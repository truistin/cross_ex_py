import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from model.model import Balance, WithdrawalStatus, Status, Position, Chain

class BinanceMgr():
    def __init__(self, api_key, secrect_key, passphrase = ''):
        self.api_key = api_key
        self.secrect_key = secrect_key
        self.passphrase = passphrase
    
    def fetch_pairs_info(self):
        pass
    
    def fetch_now_px(self):
        resp = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex").json()
        px_map = {}
        for item in resp:
            px_map[item['symbol']] = float(item['indexPrice'])
        return px_map

    def gen_sign(self, params):
        query = urlencode(params)
        signature = hmac.new(
            self.secrect_key.encode(),
            query.encode(),
            hashlib.sha256
        ).hexdigest()
        return query + "&signature=" + signature
    
    def fetch_spot_balance(self): ##资金账户
        params = {}
        params["timestamp"] = int(time.time() * 1000)
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}

        url = "https://api.binance.com" + "/sapi/v1/asset/get-funding-asset" + "?" + query_with_sig
        resp = requests.post(url, headers=headers).json()
        #print(resp)
        bal = Balance()
        for item in resp:
            if item['asset'] == 'USDT':
                bal.currency = item['asset']
                bal.available = float(item['free'])
                bal.locked = float(item['locked'])
                bal.equity = bal.available + bal.locked
                #print(bal)
                return bal
        return bal

    def set_leverage(self, symbol, leverage):
        params = {}
        params["timestamp"] = int(time.time() * 1000)
        params['symbol'] = symbol
        params['leverage'] = int(leverage)
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}
        url = "https://fapi.binance.com" + "/fapi/v1/leverage" + "?" + query_with_sig
        resp = requests.post(url, headers=headers).json()
        return resp

    def fetch_future_balance(self):
        params = {}
        params["timestamp"] = int(time.time() * 1000)
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}

        url = "https://fapi.binance.com" + "/fapi/v3/balance" + "?" + query_with_sig
        resp = requests.get(url, headers=headers).json()
        #print(resp)
        bal = Balance()
        for item in resp:
            if item['asset'] == 'USDT':
                bal.currency = item['asset']
                bal.available = float(item['maxWithdrawAmount'])
                bal.locked = 0.0
                bal.equity = float(item['crossWalletBalance']) + float(item['crossUnPnl'])
                print(bal)
                return bal
        return bal

    def asset_transfer_inner(self, coin, from_field, to_field, amount):
        params = {}
        params["timestamp"] = int(time.time() * 1000)
        params['asset'] = coin
        params['amount'] = float(amount)
        if from_field == 'spot': #资金钱包转化U合约
            params['type'] = 'FUNDING_UMFUTURE'
        else: #U合约转化资金钱包
            params['type'] = 'UMFUTURE_FUNDING'
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}
        url = "https://api.binance.com" + "/sapi/v1/asset/transfer" + "?" + query_with_sig
        resp = requests.post(url, headers=headers).json()
        print(resp) 
        if 'code' in resp.keys(): #错误
            return 1, resp
        else:
            return 0, resp #划转成功

    ##提现
    def withdrawals(self, coin, to_exch, address, chain, amount):
        params = {}
        params["timestamp"] = int(time.time() * 1000)
        params["coin"] = coin
        params["withdrawOrderId"] = "binance_withdrawals_" + str(int(time.time() * 1000))
        if chain == Chain.TRC20:
            params["network"] = 'TRX'
        elif chain == Chain.ERC20:
            params["network"] = 'ETH'
        params["address"] = address
        params["amount"] = amount
        params["walletType"] = 1
        query_with_sig = self.gen_sign(params)
        headers = {"X-MBX-APIKEY": self.api_key}
        url = "https://api.binance.com" + "/sapi/v1/capital/withdraw/apply" + "?" + query_with_sig
        resp = requests.post(url, headers=headers).json()
        status = Status.PENDING
        msg = ''
        if 'id' not in resp:
            status = Status.FAIL
            msg = resp
            id = '0'
        else:
            id = resp['id']
        print('resp:', resp)
        return WithdrawalStatus(
                currency=coin, tx_id=id, withdraw_clt_id=params['withdrawOrderId'], 
                amount=params['amount'], to_exch= to_exch, address=address, chain=chain, status=status, msg=msg)


    ##提现记录
    def query_withdrawals_record(self, withdraw_clt_id):
        params = {}
        params["timestamp"] = int(time.time() * 1000)
        params["coin"] = "USDT"
        params["withdrawOrderId"] = withdraw_clt_id
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}

        url = "https://api.binance.com" + "/sapi/v1/capital/withdraw/history" + "?" + query_with_sig
        resp = requests.get(url, headers=headers).json()
        print(resp)
        for item in resp:
            if item['withdrawOrderId'] == withdraw_clt_id:
                if item['status'] == 0:
                    return Status.PENDING, f"已发送确认Email({item['status']})"
                elif item['status'] == 2:
                    return Status.PENDING, f"等待确认({item['status']})"
                elif item['status'] == 4:
                    return Status.PENDING, f"处理中({item['status']})"
                elif item['status'] == 3:
                    return Status.FAIL, f"被拒绝({item['status']})"
                elif item['status'] == 6:
                    return Status.SUCC, f"提现完成({item['status']})"
        return Status.FAIL, f'not found binance withdrawals_record {withdraw_clt_id}'

    ##入金记录
    def query_desposite_record(self, tx_id):
        params = {}
        params["timestamp"] = int(time.time() * 1000)
        params["coin"] = "USDT"
        params["txId"] = tx_id
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}

        url = "https://api.binance.com" + "/sapi/v1/capital/deposit/hisrec" + "?" + query_with_sig
        resp = requests.get(url, headers=headers).json()
        for item in resp:
            if item['txId'] == tx_id:
                if item['status'] in (0, 6, 8):
                    return Status.PENDING, item['status']
                elif item['status'] in (2, 7):
                    return Status.FAIL, itenm['status']
                elif item['status'] == 1:
                    return Status.SUCC, item['status']
        return Status.FAIL, f'not found binance desposite_record {tx_id}'

     ##获取合约持仓
    def get_future_pos(self):
        params = {}
        positions = {}
        params["timestamp"] = int(time.time() * 1000)
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}

        url = "https://fapi.binance.com" + "/fapi/v2/positionRisk" + "?" + query_with_sig
        resp = requests.get(url, headers=headers).json()
        for item in resp:
            pos = Position(symbol = item['symbol'], size = float(item['positionAmt']), entry_price = float(item['entryPrice']), liq_price = float(item['liquidationPrice']), leverage = float(item['leverage']), now_price = float(item['markPrice']))
            positions[item['symbol']] = pos
        return positions

    ##获取网上链路信息
    def get_chain_info(self):
        params = {}
        positions = {}
        params["timestamp"] = int(time.time() * 1000)
        query_with_sig = self.gen_sign(params)

        headers = {"X-MBX-APIKEY": self.api_key}

        url = "https://api.binance.com" + "/sapi/v1/capital/config/getall" + "?" + query_with_sig
        resp = requests.get(url, headers=headers).json()
        #print(resp)
        for item in resp:
            if item['coin'] == 'USDT':
                for v in item['networkList']:
                    print(v['network'], v['name'])
                #print(item)
                return
        