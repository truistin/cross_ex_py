from exchanges.gate.gate_mgr import GateMgr
from exchanges.kraken.kraken_mgr import KrakenMgr
from exchanges.binance.binance_mgr import BinanceMgr
from exchanges.kucoin.kucoin_mgr import KucoinMgr
from exchanges.okex.okex_mgr import OkexMgr
from model.model import Exchange, NeedTransfer, Chain, Status, format_symbol
import time
from pymongo import MongoClient
import sys, logging, os
from logging.handlers import TimedRotatingFileHandler

EXCHANGE_MGR = {
    Exchange.BINANCE: BinanceMgr,
    Exchange.OKEX: OkexMgr,
    Exchange.GATE: GateMgr,
    Exchange.KUCOIN: KucoinMgr,
    Exchange.KRAKEN: KrakenMgr,
}

def logs_init_std(file_name):
    file_name = file_name.replace(':', '_')
    base_path = 'logs'
    log_file_name = os.path.join(base_path, file_name) + '.log'
    log_dir_name = os.path.dirname(log_file_name)

    if not os.path.exists(log_dir_name):
        os.makedirs(log_dir_name)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    log_formatter = logging.Formatter(
        '%(asctime)s@%(filename)s/%(funcName)s %(message)s')
    file_handler = TimedRotatingFileHandler(log_file_name,
                                            when="midnight",
                                            backupCount=3)
    file_handler.setFormatter(log_formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

class Strategy:
    need_transfer = {}
    can_transfer = {}
    exch_mgr = {}
    exch_pos = {}  ##合约仓位
    exch_spot_bal = {}
    exch_future_bal = {}
    exch_im = {}
    exch_addr = {}
    exch_withdraw_record = {}
    available_factor = 1 * 2.5 #可以转账
    transfer_factor = 0.5 * 2.5 #转账 杠杆10倍， 离爆仓还有10个点就转账  最多开四倍杠杆
    adl_factor = 0.25 * 2.5 #强平 杠杆10倍， 离爆仓还有5个点就强平 强平在交易程序里进行，不在这里
    min_transfer_amt = 0 #最小划转额度

    def __init__(self, username, mongodb_uri):
        self.logger = logging.getLogger(f'{username}_exch_funding')
        mongo_clt = MongoClient('mongodb://admin:ceff12343@3.114.59.95:27179')
        client = username.split('_')[0]
        name = username.split('_')[1]
        secrets_db = mongo_clt["Secrets_exch"][client]
        deploy_db = mongo_clt["Strategy_deploy_exch"][client]
        orch_db = mongo_clt["Strategy_orch_exch"][client]
        orch_doc = orch_db.find_one({"$and":[{"orch": True}, {"_id":{"$regex":f'{username}@exch_funding'}}]})
        if orch_doc != None:
            deploy_doc = deploy_db.find_one({"_id":{"$regex":f'{username}@exch_funding'}})
            self.available_factor = deploy_doc['transfer_config']['available_factor']
            self.transfer_factor = deploy_doc['transfer_config']['transfer_factor']
            self.adl_factor = deploy_doc['transfer_config']['adl_factor']
            self.min_transfer_amt = deploy_doc['transfer_config']['min_transfer_amt']
            for item in deploy_doc['secrets']:
                secret_doc = secrets_db.find_one({"_id":{"$regex":f'{item}'}})
                if secret_doc['exchange'] == 'kraken':
                    spot_secret_doc = secrets_db.find_one({"_id":{"$regex":f'{secret_doc['_id'].split(":")[0] + ":spot"}'}})
                    self.exch_mgr[Exchange(secret_doc['exchange'])] = EXCHANGE_MGR[Exchange(secret_doc['exchange'])](
                            future_api_key = secret_doc['api_key'], 
                            future_secrect_key = secret_doc['secret_key'], 
                            future_passphrase = secret_doc['passphrase'],
                            spot_api_key = spot_secret_doc['api_key'],
                            spot_secrect_key = spot_secret_doc['secret_key'],
                            spot_passphrase = spot_secret_doc['passphrase'])
                else:
                    self.exch_mgr[Exchange(secret_doc['exchange'])] = EXCHANGE_MGR[Exchange(secret_doc['exchange'])](api_key=secret_doc['api_key'], secrect_key=secret_doc['secret_key'], passphrase=secret_doc['passphrase'])

                self.exch_addr[Exchange(secret_doc['exchange'])] = {}
                self.exch_addr[Exchange(secret_doc['exchange'])][Chain.ERC20] = (secret_doc['address']['erc20']['addr_name'], secret_doc['address']['erc20']['addr'])
                self.exch_addr[Exchange(secret_doc['exchange'])][Chain.TRC20] = (secret_doc['address']['trc20']['addr_name'], secret_doc['address']['trc20']['addr'])
        else:
            self.logger.error("orch_doc is None")
            raise ValueError("orch_doc is None")

        for item in deploy_doc['pair_configs']:
            symbol = format_symbol(Exchange(item['master_pair'].split(':')[0]), item['master_pair'].split(':')[2])
            resp = self.exch_mgr[Exchange(item['master_pair'].split(':')[0])].set_leverage(symbol, item['master_leverage'])
            self.logger.info(f"{Exchange(item['master_pair'].split(':')[0])} set leverage resp: {resp}")
            symbol = format_symbol(Exchange(item['slave_pair'].split(':')[0]), item['slave_pair'].split(':')[2])
            resp = self.exch_mgr[Exchange(item['slave_pair'].split(':')[0])].set_leverage(symbol, item['slave_leverage'])
            self.logger.info(f"{Exchange(item['slave_pair'].split(':')[0])} set leverage resp: {resp}")

        for exch, mgr in self.exch_mgr.items():
            mgr.fetch_pairs_info()
            self.exch_spot_bal[exch] = mgr.fetch_spot_balance()
            self.logger.info(f'{exch} spot_usdt_bal: {self.exch_spot_bal[exch]}')
            if self.exch_spot_bal[exch].available > 1.0 :
                code, msg = mgr.asset_transfer_inner('USDT', 'spot', 'futures', self.exch_spot_bal[exch].available)
                if code != 0:
                    self.logger.warning(f'{exch} transfer from spot to future fail, msg: {msg}')

        px_map = {}
        for exch, mgr in self.exch_mgr.items():
            px_map[exch] = mgr.fetch_now_px()
            self.exch_im[exch] = 0.0
        for item in deploy_doc['pair_configs']:
            exch = Exchange(item['master_pair'].split(':')[0])
            symbol = item['master_pair'].split(':')[2]
            px = px_map[exch][format_symbol(exch, symbol)]
            self.exch_im[exch] += float(px) * float(item['max_pos_base_amount']) / float(item['master_leverage'])
            exch = Exchange(item['slave_pair'].split(':')[0])
            symbol = item['slave_pair'].split(':')[2]
            px = px_map[exch][format_symbol(exch, symbol)]
            self.exch_im[exch] += float(px) * float(item['max_pos_base_amount']) / float(item['slave_leverage'])
        print(self.exch_im)

        
    def verify_transfer(self, exchange):
        if self.exch_future_bal[exchange].equity < self.transfer_factor * self.exch_im[exchange]:  ##需要转账金额
            #del self.can_transfer[exchange]
            if exchange not in self.need_transfer.keys() \
               and exchange not in self.can_transfer.keys():
                need_transfer_amt = self.available_factor * self.exch_im[exchange] - self.exch_future_bal[exchange].equity
                if need_transfer_amt > self.min_transfer_amt:
                    self.need_transfer[exchange] = {}
                    self.need_transfer[exchange]['status'] = NeedTransfer.NEW
                    self.need_transfer[exchange]['amt'] = need_transfer_amt
        else: ##不需要转账金额
            if exchange not in self.can_transfer.keys() \
               and exchange not in self.need_transfer.keys() \
               and self.exch_future_bal[exchange].equity > self.available_factor * self.exch_im[exchange]: ## 有富余 可以转账
                    self.can_transfer[exchange] = min(self.exch_future_bal[exchange].available, self.exch_future_bal[exchange].equity - self.available_factor * self.exch_im[exchange])

    def transfer_chain(self, coin, from_exch, to_exch, amount, withdraw_clt_id):
        add_len = len(self.exch_addr[from_exch])
        if withdraw_clt_id == None: ##每个链都转一下
            self.exch_withdraw_record[from_exch] = {}
            for chain, addr in self.exch_addr[from_exch].items():
                self.need_transfer[to_exch]['status'] = NeedTransfer.PENDING
                res = self.exch_mgr[from_exch].withdrawals(coin=coin, to_exch=to_exch, address=addr, chain=chain, amount=int(amount/add_len))
                self.exch_withdraw_record[from_exch][res.withdraw_clt_id] = res
        else: ##单独转一个链
            res = self.exch_mgr[from_exch].withdrawals(coin=coin, to_exch=to_exch, address=self.exch_withdraw_record[from_exch][withdraw_clt_id].address, chain=self.exch_withdraw_record[from_exch][withdraw_clt_id].chain, amount=amount)
            self.exch_withdraw_record[from_exch][res.withdraw_clt_id] = res

    def run(self):
        for key, val in self.exch_mgr.items():
            self.exch_future_bal[key] = val.fetch_future_balance()
            self.exch_pos[key] = val.get_future_pos()
            self.exch_im[key] = sum( abs(p['size']) * p['now_price'] / p['leverage'] for p in self.exch_pos[key])
            self.verify_transfer(key)
        sorted_need = sorted(self.need_transfer.items(), key = lambda x: x[1]['amt'], resverse=True)
        for need_exch, need_val in self.sorted_need.items():
            if need_val['status'] == NeedTransfer.NEW: ##准备划转, 先将资金转入现货
                sorted_can = sorted(self.can_transfer.items(), key = lambda x: x[1], resverse=True)
                can_exch, can_val = next(iter(sorted_can.items()))
                transfer_amt = min(can_val, need_val['amt'])
                if transfer_amt < self.min_transfer_amt:
                    continue
                self.need_transfer[need_exch]["amt"] -= transfer_amt
                self.can_transfer[can_exch] -= transfer_amt
                code, msg = self.exch_mgr[can_exch].asset_transfer_inner('USDT', 'futures', 'spot', transfer_amt)
                if code != 0:
                    self.logger.error(f'{can_exch} transfer from future to spot fail, msg: {msg}')
                else:  ##合约转账现货成功
                    for i in range(5):
                        time.sleep(1)
                        spot_bal = self.exch_mgr[can_exch].fetch_spot_balance()
                        if spot_bal.available < transfer_amt:
                            self.logger.warning(f'{can_exch} transfer from future to spot error, need {transfer_amt} but {spot_bal.available}')
                        if spot_bal.available > 0:
                            break
                    if spot_bal.available == 0:
                        continue
                    self.transfer_chain(coin='USDT', from_exch=can_exch, to_exch=need_exch, amount=spot_bal.available, withdraw_clt_id = None)
        for exch, mgr in self.exch_mgr.items():
            if exch in self.exch_withdraw_record.keys():  ##检查交易所是否在跨所转账
                for clt_id,_ in self.exch_withdraw_record[exch].items():
                    if self.exch_withdraw_record[exch][clt_id].status in (Status.CANCEL, Status.FAIL): ##转账失败，重新转
                        self.logger.warning(f'{exch} transfer to {self.exch_withdraw_record[exch][clt_id].to_exch} fail, chain:{self.exch_withdraw_record[exch][clt_id].chain} status:{self.exch_withdraw_record[exch][clt_id].status}')
                        self.transfer_chain(coin='USDT', from_exch=exch, to_exch=self.exch_withdraw_record[exch][clt_id].to_exch, amount=self.exch_withdraw_record[exch][clt_id].amount, withdraw_clt_id = self.exch_withdraw_record[exch][clt_id].withdraw_clt_id)
                    elif self.exch_withdraw_record[exch][clt_id].status == Status.SUCC: ##转账成功
                        desposite_status, msg = self.exch_mgr[self.exch_withdraw_record[exch][clt_id].to_exch].query_desposite_record(self.exch_withdraw_record[exch][clt_id].tx_id) #充值状态
                        if desposite_status == Status.FAIL: #充值失败
                            print(f'{exch} transfer to {self.exch_withdraw_record[exch][clt_id].to_exch} SUCC, but query deposite_record fail, msg:{msg}')
                            self.exch_withdraw_record[exch][clt_id].status = Status.FAIL
                        elif desposite_status == Status.PENDING: #充值中
                            self.exch_withdraw_record[exch][clt_id].status = Status.PENDING
                        elif desposite_status == Status.SUCC: #充值成功
                            spot_bal = self.exch_mgr[self.exch_withdraw_record[exch][clt_id].to_exch].fetch_spot_balance()
                            code, msg = self.exch_mgr[self.exch_withdraw_record[exch][clt_id].to_exch].asset_transfer_inner(self.exch_withdraw_record[exch][clt_id].currency, 'spot', 'future', spot_bal.available)
                            if code != 0:  #内部转账失败
                                print(f'{self.exch_withdraw_record[exch][clt_id].to_exch} transfer from spot to future fail, msg: {msg}')
                            else: #内部转账成功
                                del self.exch_withdraw_record[exch][clt_id]
                                if len(self.exch_withdraw_record[exch] == 0):
                                    del self.exch_withdraw_record[exch]
                                    del self.can_transfer[exch]
                                    del self.need_transfer[self.exch_withdraw_record[exch][clt_id].to_exch]
                    elif self.exch_withdraw_record[exch][clt_id].status == Status.PENDING: ##转账中
                        status, msg = mgr.query_withdrawals_record(self.exch_withdraw_record[exch][clt_id].currency, self.exch_withdraw_record[exch][clt_id].withdraw_clt_id)
                        if status == Status.FAIL: ##转账失败，继续转账
                            print(f'{exch} transfer to {self.exch_withdraw_record[exch][clt_id].to_exch} fail, chain:{self.exch_withdraw_record[exch][clt_id].chain} msg:{msg}')
                            self.exch_withdraw_record[exch][clt_id].status = Status.FAIL
                        elif status == Status.SUCC: #转账成功
                            self.exch_withdraw_record[exch][clt_id].status = Status.SUCC
                            if exch == Exchange.OKEX:
                                self.exch_withdraw_record[exch][clt_id].tx_id = msg['data'][0]['txId']
                            elif exch == Exchange.KUCOIN:
                                self.exch_withdraw_record[exch][clt_id].tx_id = msg['data']['walletTxId']
                            elif exch == Exchange.KRAKEN:
                                self.exch_withdraw_record[exch][clt_id].tx_id = msg['txid']
        time.sleep(10)


##/opt/homebrew/Caskroom/miniconda/base/bin/python3
#python3 main.py teff_teff001 mongodb://admin:ceff12343@3.114.59.95:27179
if __name__ == "__main__":
    
    username = sys.argv[1]
    mongodb_uri = sys.argv[2]
    logs_init_std(f'{username}_exch_funding')
    strategy = Strategy(username, mongodb_uri)
    
    '''
    mgr = KucoinMgr("", "", "")
    px = mgr.fetch_now_px()
    print(px)
    '''
    