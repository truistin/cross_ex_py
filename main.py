from exchanges.gate.gate_mgr import GateMgr
from exchanges.kraken.kraken_mgr import KrakenMgr
from exchanges.binance.binance_mgr import BinanceMgr
from exchanges.kucoin.kucoin_mgr import KucoinMgr
from exchanges.okex.okex_mgr import OkexMgr
from influxdb import InfluxDBClient
from model.model import Exchange, NeedTransfer, Chain, Status, format_symbol,format_symbol_standard, Position
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
    run_status = 0
    influx_clt = None
    username = ""
    cfg_symbols = []
    transfer_fee = 5


    def __init__(self, username, mongodb_uri):
        try:
            self.username = username
            self.logger = logging.getLogger(f'{username}_exch_funding')
            self.logger.info(f"username:{username}, mongodb_uri:{mongodb_uri}")
            mongo_clt = MongoClient(mongodb_uri)
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
                        spot_secret_doc = secrets_db.find_one({"_id":{"$regex":f'{secret_doc["_id"].split(":")[0] + ":spot"}'}})
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
                    #ERC20暂时先不弄
                    #self.exch_addr[Exchange(secret_doc['exchange'])][Chain.ERC20] = (secret_doc['address']['erc20']['addr_name'], secret_doc['address']['erc20']['addr'])
                    self.exch_addr[Exchange(secret_doc['exchange'])][Chain.TRC20] = (secret_doc['address']['trc20']['addr_name'], secret_doc['address']['trc20']['addr'])
            else:
                self.logger.error("orch_doc is None")
                raise ValueError("orch_doc is None")
            influx_json = mongo_clt["DataSource"]["influx"].find_one({"_id":{"$regex": f".*account_data$"}})
            self.influx_clt = InfluxDBClient(host = influx_json["host"], port = influx_json["port"], username = influx_json["username"], password = influx_json["password"], database = influx_json["database"], ssl = influx_json["ssl"])
            
            for item in deploy_doc['pair_configs']:
                symbol = format_symbol(Exchange(item['master_pair'].split(':')[0]), item['master_pair'].split(':')[2])
                self.cfg_symbols.append((symbol, Exchange(item['master_pair'].split(':')[0])))
                resp = self.exch_mgr[Exchange(item['master_pair'].split(':')[0])].set_leverage(symbol, item['master_leverage'])
                self.logger.info(f"{Exchange(item['master_pair'].split(':')[0])} set leverage resp: {resp}")
                symbol = format_symbol(Exchange(item['slave_pair'].split(':')[0]), item['slave_pair'].split(':')[2])
                self.cfg_symbols.append((symbol, Exchange(item['slave_pair'].split(':')[0])))
                resp = self.exch_mgr[Exchange(item['slave_pair'].split(':')[0])].set_leverage(symbol, item['slave_leverage'])
                self.logger.info(f"{Exchange(item['slave_pair'].split(':')[0])} set leverage resp: {resp}")

            for exch, mgr in self.exch_mgr.items():
                mgr.fetch_pairs_info()
                resp = mgr.set_pos_mode()
                self.logger.info(f'{exch} set_pos_mode: {resp}')
                self.exch_spot_bal[exch] = mgr.fetch_spot_balance()
                self.logger.info(f'{exch} spot_usdt_bal: {self.exch_spot_bal[exch]}')
                if self.exch_spot_bal[exch].available > 1.0 :
                    code, msg = mgr.asset_transfer_inner('USDT', 'spot', 'futures', self.exch_spot_bal[exch].available)
                    if code != 0:
                        self.logger.warning(f'{exch} transfer from spot to future fail, msg: {msg}')
                    else:
                        self.logger.info(f'{exch} transfer from spot to future succ, msg: {msg}')

            for exch, mgr in self.exch_mgr.items():
                self.exch_im[exch] = 0.0
            for item in deploy_doc['pair_configs']:
                exch = Exchange(item['master_pair'].split(':')[0])
                symbol = item['master_pair'].split(':')[2]
                self.exch_im[exch] += abs(float(item['max_pos_notional'])) / float(item['master_leverage'])
                exch = Exchange(item['slave_pair'].split(':')[0])
                symbol = item['slave_pair'].split(':')[2]
                self.exch_im[exch] += abs(float(item['max_pos_notional'])) / float(item['slave_leverage'])
        except Exception as e:
            self.logger.exception(f"error: {e}")

    def record_influxdb(self):
        if len(self.exch_withdraw_record) == 0:
            all_future_bal = 0.0
            points = []
            for exch, mgr in self.exch_mgr.items():
                principals_amounts = {}
                future_bal = mgr.fetch_future_balance()
                principals_amounts["usdt"] = future_bal.equity
                all_future_bal += future_bal.equity
                tags = {
                    "client": self.username.split('_')[0],
                    "username": self.username.split('_')[1],
                    "exchange": exch.value,
                }
                point = {"measurement": "balance_exch", "tags":tags, "fields":principals_amounts}
                points.append(point)

            principals_amounts = {}
            tags = {
                "client": self.username.split('_')[0],
                "username": self.username.split('_')[1],
                "exchange": "all",
            }
            principals_amounts["usdt"] = all_future_bal
            point = {"measurement": "balance_exch", "tags":tags, "fields":principals_amounts}
            points.append(point)
            self.influx_clt.write_points(points, time_precision="ms")

        points = []
        trade_symbols = []
        for exch, mgr in self.exch_mgr.items():
            future_pos = mgr.get_future_pos()
            for symbol, pos in future_pos.items():
                trade_symbols.append((symbol, exch))
                tags = {
                    "client": self.username.split('_')[0],
                    "username": self.username.split('_')[1],
                    "exchange": exch.value,
                    "pair": format_symbol_standard(exch, pos.symbol),
                }
                fields = {}
                fields['entry_price'] = pos.entry_price
                fields['size'] = pos.size
                point = {"measurement": "position_exch", "tags":tags, "fields":fields}
                points.append(point)
        res = list(set(self.cfg_symbols) - set(trade_symbols))
        #self.logger.info(f"{self.cfg_symbols}   {trade_symbols}  {res}")
        for symbol, exch in res:
            tags = {
                "client": self.username.split('_')[0],
                "username": self.username.split('_')[1],
                "exchange": exch.value,
                "pair": format_symbol_standard(exch, symbol)
            }
            fields = {}
            fields['entry_price'] = 0.0
            fields['size'] = 0.0
            point = {"measurement": "position_exch", "tags":tags, "fields":fields}
            points.append(point)
        resp = self.influx_clt.write_points(points, time_precision="ms")

    def verify_transfer(self, exchange):
        if self.exch_future_bal[exchange].equity < self.transfer_factor * self.exch_im[exchange]:  ##需要转账金额
            #del self.can_transfer[exchange]
            if exchange not in self.need_transfer.keys() \
               and exchange not in self.can_transfer.keys():
                need_transfer_amt = self.available_factor * self.exch_im[exchange] - self.exch_future_bal[exchange].equity
                if need_transfer_amt > self.min_transfer_amt:
                    self.need_transfer[exchange] = {}
                    self.need_transfer[exchange]['status'] = NeedTransfer.NEW
                    self.need_transfer[exchange]['amt'] = round(need_transfer_amt)
        else: ##不需要转账金额
            if exchange not in self.can_transfer.keys() \
               and exchange not in self.need_transfer.keys() \
               and self.exch_future_bal[exchange].equity > self.available_factor * self.exch_im[exchange]: ## 有富余 可以转账
                    amt = min(round(self.exch_future_bal[exchange].available), round(self.exch_future_bal[exchange].equity - self.available_factor * self.exch_im[exchange]))
                    if amt > self.min_transfer_amt:
                        self.can_transfer[exchange] = amt

    def transfer_chain(self, coin, from_exch, to_exch, amount, withdraw_clt_id):
        self.logger.info(f"transfer_chain request: {coin}, from_exch: {from_exch}, to_exch:{to_exch}, amount:{amount}, withdraw_clt_id:{withdraw_clt_id}")
        add_len = len(self.exch_addr[from_exch])
        if withdraw_clt_id == None: ##每个链都转一下
            if from_exch not in self.exch_withdraw_record.keys():
                self.exch_withdraw_record[from_exch] = {}
            for chain, addr in self.exch_addr[to_exch].items():
                if from_exch == Exchange.KRAKEN:
                    transfer_addr = addr[0]
                else:
                    transfer_addr = addr[1]
                self.need_transfer[to_exch]['status'] = NeedTransfer.PENDING
                res = self.exch_mgr[from_exch].withdrawals(coin=coin, to_exch=to_exch, address=transfer_addr, chain=chain, amount=int(amount/add_len))
                self.exch_withdraw_record[from_exch][res.withdraw_clt_id] = res
                self.logger.info(f"transfer_chain response({addr}): {res}")
        else: ##单独转一个链
            res = self.exch_mgr[from_exch].withdrawals(coin=coin, to_exch=to_exch, address=self.exch_withdraw_record[from_exch][withdraw_clt_id].address, chain=self.exch_withdraw_record[from_exch][withdraw_clt_id].chain, amount=amount)
            self.exch_withdraw_record[from_exch][res.withdraw_clt_id] = res
            self.logger.info(f"transfer_chain response({self.exch_withdraw_record[from_exch][withdraw_clt_id].address}): {res}")

    def run(self):
        while True:
            time_period = 15
            try:
                del_withdraw_record = {}
                for exch, mgr in self.exch_mgr.items():
                    self.exch_future_bal[exch] = mgr.fetch_future_balance()
                    self.logger.info(f'{exch} future_bal: {self.exch_future_bal[exch]}')
                    self.exch_pos[exch] = mgr.get_future_pos()
                    self.logger.info("%s future_pos:\n%s",exch,"\n".join(str(p) for p in self.exch_pos[exch].values()))
                    if self.run_status != 0:
                        self.exch_im[exch] = sum( abs(p.size) * p.now_price / p.leverage for p in self.exch_pos[exch].values())
                    self.logger.info(f'{exch} exch_im: {self.exch_im[exch]}')
                    self.verify_transfer(exch)
                self.run_status = 1
                sorted_need = dict(sorted(self.need_transfer.items(), key = lambda x: x[1]['amt'], reverse=True))
                self.logger.info(f"need_transfer:{self.need_transfer}, can_transfer:{self.can_transfer}")
                for need_exch, need_val in sorted_need.items():
                    if need_val['status'] == NeedTransfer.NEW: ##准备划转, 先将资金转入现货
                        sorted_can = dict(sorted(self.can_transfer.items(), key = lambda x: x[1], reverse=True))
                        if not sorted_can:
                            self.logger.warning("can_transfer is Null")
                            break
                        can_exch, can_val = next(iter(sorted_can.items()))
                
                        if can_val - self.transfer_fee < need_val['amt'] :
                            transfer_amt = can_val - self.transfer_fee ##跨所转账数量
                            inner_transfer_amt = can_val  ##内部转账数量
                        else:
                            transfer_amt = need_val['amt']
                            inner_transfer_amt = need_val['amt'] + self.transfer_fee
                        if transfer_amt < self.min_transfer_amt:
                            continue
                        self.need_transfer[need_exch]["amt"] -= transfer_amt
                        self.can_transfer[can_exch] -= transfer_amt.max(inner_transfer_amt)
                        code, msg = self.exch_mgr[can_exch].asset_transfer_inner('USDT', 'futures', 'spot', inner_transfer_amt)
                        if code != 0:
                            self.logger.error(f'{can_exch} transfer from future to spot fail, msg: {msg}')
                        else:  ##合约转账现货成功
                            self.logger.info(f'{can_exch} transfer from future to spot succ, msg: {msg}')
                            for i in range(5):
                                time.sleep(1)
                                self.exch_spot_bal[can_exch] = self.exch_mgr[can_exch].fetch_spot_balance()
                                if self.exch_spot_bal[can_exch].available >= inner_transfer_amt * 0.99:
                                    break
                            if self.exch_spot_bal[can_exch].available < inner_transfer_amt * 0.99:
                                self.logger.warning(f'{can_exch} transfer from future to spot error, need {inner_transfer_amt} but {self.exch_spot_bal[can_exch].available}')
                                continue
                            self.transfer_chain(coin='USDT', from_exch=can_exch, to_exch=need_exch, amount=self.exch_spot_bal[can_exch].available - self.transfer_fee, withdraw_clt_id = None)
                for exch, mgr in self.exch_mgr.items():
                    if  exch in self.need_transfer.keys() and exch not in {record.to_exch for records_map in self.exch_withdraw_record.values() for record in records_map.values()} :
                        del self.need_transfer[exch]
                    if exch in self.can_transfer.keys() and exch not in self.exch_withdraw_record.keys():
                        del self.can_transfer[exch]
                    if exch not in self.need_transfer.keys() and exch not in self.can_transfer.keys():
                        self.exch_spot_bal[exch] = mgr.fetch_spot_balance()
                        self.logger.info(f'{exch} spot_bal: {self.exch_spot_bal[exch]}')
                        if self.exch_spot_bal[exch].available > 1.0 :
                            code, msg = mgr.asset_transfer_inner('USDT', 'spot', 'futures', round(self.exch_spot_bal[exch].available))
                            if code != 0:
                                self.logger.warning(f'{exch} transfer from spot to future fail, msg: {msg}')
                            else:
                                self.logger.info(f'{exch} transfer from spot to future succ, msg: {msg}')
                    if exch in self.exch_withdraw_record.keys():  ##检查交易所是否在跨所转账
                        for clt_id,_ in list(self.exch_withdraw_record[exch].items()):
                            if self.exch_withdraw_record[exch][clt_id].status in (Status.CANCEL, Status.FAIL): ##转账失败，重新转
                                self.logger.warning(f'{exch} transfer to {self.exch_withdraw_record[exch][clt_id].to_exch} {self.exch_withdraw_record[exch][clt_id].status}, chain:{self.exch_withdraw_record[exch][clt_id].chain}')
                                self.transfer_chain(coin='USDT', from_exch=exch, to_exch=self.exch_withdraw_record[exch][clt_id].to_exch, amount=self.exch_withdraw_record[exch][clt_id].amount, withdraw_clt_id = self.exch_withdraw_record[exch][clt_id].withdraw_clt_id)
                            elif self.exch_withdraw_record[exch][clt_id].status == Status.SUCC: ##转账成功
                                desposite_status, msg = self.exch_mgr[self.exch_withdraw_record[exch][clt_id].to_exch].query_desposite_record(self.exch_withdraw_record[exch][clt_id].tx_id) #充值状态
                                self.logger.info(f'query_desposite_record {exch} transfer to {self.exch_withdraw_record[exch][clt_id].to_exch} {desposite_status}, chain:{self.exch_withdraw_record[exch][clt_id].chain}, msg:{msg}')
                                if desposite_status == Status.FAIL: #充值失败
                                    self.exch_withdraw_record[exch][clt_id].status = Status.FAIL
                                elif desposite_status == Status.PENDING: #充值中
                                    time_period = 5
                                    self.exch_withdraw_record[exch][clt_id].status = Status.PENDING
                                elif desposite_status == Status.SUCC: #充值成功
                                    self.exch_spot_bal[self.exch_withdraw_record[exch][clt_id].to_exch] = self.exch_mgr[self.exch_withdraw_record[exch][clt_id].to_exch].fetch_spot_balance()
                                    if self.exch_spot_bal[self.exch_withdraw_record[exch][clt_id].to_exch].available > 1.0 :
                                        code, msg = self.exch_mgr[self.exch_withdraw_record[exch][clt_id].to_exch].asset_transfer_inner(self.exch_withdraw_record[exch][clt_id].currency, 'spot', 'futures', self.exch_spot_bal[self.exch_withdraw_record[exch][clt_id].to_exch].available)
                                        if code != 0:  #内部转账失败
                                            self.logger.warning(f'{self.exch_withdraw_record[exch][clt_id].to_exch} transfer from spot to future fail, msg: {msg}')
                                        else: #内部转账成功
                                            self.logger.info(f'{self.exch_withdraw_record[exch][clt_id].to_exch} transfer from spot to future succ, msg: {msg}')
                                            del_withdraw_record[exch] = clt_id
                            elif self.exch_withdraw_record[exch][clt_id].status == Status.PENDING: ##转账中
                                status, msg = mgr.query_withdrawals_record(self.exch_withdraw_record[exch][clt_id].withdraw_clt_id)
                                if status == Status.FAIL: ##转账失败，继续转账
                                    self.exch_withdraw_record[exch][clt_id].status = Status.FAIL
                                elif status == Status.SUCC: #转账成功
                                    self.exch_withdraw_record[exch][clt_id].status = Status.SUCC
                                    time_period = 5
                                    if exch == Exchange.OKEX:
                                        self.exch_withdraw_record[exch][clt_id].tx_id = msg['data'][0]['txId']
                                    elif exch == Exchange.BINANCE:
                                        self.exch_withdraw_record[exch][clt_id].tx_id = msg['txId']
                                    elif exch == Exchange.KUCOIN:
                                        self.exch_withdraw_record[exch][clt_id].tx_id = msg['data']['walletTxId']
                                    elif exch == Exchange.KRAKEN:
                                        self.exch_withdraw_record[exch][clt_id].tx_id = msg['txid']
                                    elif exch == Exchange.GATE:
                                        self.exch_withdraw_record[exch][clt_id].tx_id = msg['txid']
                                self.logger.info(f'query_withdrawals_record, {exch} transfer to {self.exch_withdraw_record[exch][clt_id].to_exch} {status}, chain:{self.exch_withdraw_record[exch][clt_id].chain}, msg:{msg}')
                for exch, clt_id in del_withdraw_record.items():
                    del self.exch_withdraw_record[exch][clt_id]
                    if len(self.exch_withdraw_record[exch]) == 0:
                        del self.exch_withdraw_record[exch]
                self.record_influxdb()
                time.sleep(time_period)
            except Exception as e:
                self.logger.exception("error: %s", e)


##/opt/homebrew/Caskroom/miniconda/base/bin/python3
#python3 main.py teff_teff001 mongodb://admin:ceff12343@3.114.59.95:27179
if __name__ == "__main__":
    username = sys.argv[1]
    mongodb_uri = sys.argv[2]
    #username = 'teff_teff001'
    #mongodb_uri = 'mongodb://admin:ceff12343@3.114.59.95:27179'
    logs_init_std(f'{username}_exch_funding')
    strategy = Strategy(username, mongodb_uri)
    strategy.run()
    
    


    '''
    kucoin_mgr = KucoinMgr(api_key = "6894bd32c714e80001ef887a",
                            secrect_key = "6f307557-c4a5-4d54-a28c-da40124dc700",
                            passphrase = "Nfx921011.")
    #print(kucoin_mgr.asset_transfer_inner('USDT','futures', 'spot', 10))
    #kucoin_mgr.fetch_pairs_info()
    #print('future:', kucoin_mgr.fetch_future_balance())
    #print('spot:', kucoin_mgr.fetch_spot_balance())
    #print(kucoin_mgr.query_withdrawals_record('696250571d220900071d3c03'))
    #print(kucoin_mgr.asset_transfer_inner('USDT','futures', 'spot', 10))
    #print(kucoin_mgr.withdrawals('USDT', Exchange.BINANCE, 'TQeuBCiEr86yZrW86wkgvYiHtYoibKD4Y8', 'trc20', 100))
    #print(kucoin_mgr.fetch_spot_balance())
    #print("\n".join(str(p) for p in kucoin_mgr.get_future_pos().values()))
    #kucoin_mgr.place_order(symbol='SOLUSDTM', qty=1, price=100)    
    #print(kucoin_mgr.asset_transfer_inner('USDT','futures', 'spot', 10))
    
    gate_mgr = GateMgr(api_key = "9a13c50e604320bd0a2fe905d0808964", 
                       secrect_key = "d1e43148cfce36dcb869d2214851338441874edc12240126fe87d42e9b535a37", 
                       passphrase= "")
    
    #print(gate_mgr.query_withdrawals_record("gate_withdrawals_1768463080309"))
    #print(gate_mgr.asset_transfer_inner('USDT','futures', 'spot', 10))
    #gate_mgr.fetch_pairs_info()
    print(gate_mgr.fetch_future_balance())
    print(gate_mgr.fetch_spot_balance())
    #print(gate_mgr.get_future_pos())

    binance_mgr = BinanceMgr(api_key= "ObFNMbiFySvQapIuLmtx0ttUPeBfGXoUEVMTRky8ut6raHr9N9uDJXeslYrqjM7T",
                                secrect_key= "E5OA97KXT0ggGMmYbNEJl826pGl4qkP22coMZ5qNohTFxzrnBHmN0jaOwBXm1Ss6",
                                passphrase="")
    #print(binance_mgr.fetch_spot_balance())
    #print(binance_mgr.query_withdrawals_record("binance_withdrawals_1768038134159"))
    #binance_mgr.asset_transfer_inner('USDT', 'spot', 'futures',1274.9)
    #print("binance pos: \n".join(str(p) for p in binance_mgr.get_future_pos().values()))
    #im = sum( abs(p.size) * p.now_price / p.leverage for p in kraken_mgr.get_future_pos().values())
    #print(im)
    #print(binance_mgr.asset_transfer_inner('USDT','futures', 'spot', 10))
    kraken_mgr = KrakenMgr(future_api_key = "lptpBrv8o+FjaXm5FCV1CjdBS4/dlzM68teN2QBOexzKzAEvWlmQVODW", 
                            future_secrect_key = "EgH/cy89+FZMY5PYOtdF7pNJkaj7wR4APEX77dXPBgyMmZg7W9uMPVtjDA9e1pYeX2zmCYwVGzdeSytXrBv+H1De", 
                            future_passphrase = "",
                            spot_api_key='r7T8w6Q5jSXxvg/k4KP8ME5+WEs8P/pTNwcKbbo1+nDg/JmIF53isWJZ',
                            spot_secrect_key='XBg4BfZjPnQyIWQ/hbnCQ3M7X8jm9XofNwlp2m2e8RhsOUu1ummtIPGOvdNy5G/zrn6IeX+XDgjKX4ZuHGp7/A==',
                            spot_passphrase='')
    kraken_mgr.fetch_pairs_info()
    #kraken_mgr.withdrawals('USDT', Exchange.BINANCE, 'Bn_Trc20', 'trc20', 20)
    #print(kraken_mgr.query_desposite_record('f97f9e5890994b7f840e7c67498667ac'))
    #print(kraken_mgr.fetch_future_balance())
    #print(kraken_mgr.fetch_spot_balance())
    #print("kraken pos: \n".join(str(p) for p in kraken_mgr.get_future_pos().values()))
    #kraken_mgr.fetch_open_order()
    #kraken_mgr.cancel_all_order('PF_INITUSD')
    #kraken_mgr.place_order()
    '''