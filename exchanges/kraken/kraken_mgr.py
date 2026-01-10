import http.client
import urllib.request
import urllib.parse
import hashlib
import hmac
import base64
import json
import time
import requests
from model.model import Balance, WithdrawalStatus, Status, Position


class KrakenMgr():
    future_api_key: str
    future_secrect_key: str
    future_passphrase: str
    spot_api_key: str
    spot_secrect_key: str
    spot_passphrase: str
    pairs_info: dict

    def __init__(self, future_api_key, spot_api_key, spot_secrect_key, future_secrect_key, future_passphrase = '',spot_passphrase = ''):
        self.future_api_key = future_api_key
        self.future_secrect_key = future_secrect_key
        self.future_passphrase = future_passphrase
        self.spot_api_key = spot_api_key
        self.spot_secrect_key = spot_secrect_key
        self.spot_passphrase = spot_passphrase
        self.pairs_info = {}

    def fetch_now_px(self):
        resp = requests.get("https://futures.kraken.com/derivatives/api/v3/tickers").json()
        px_map = {}
        for item in resp['tickers']:
            px_map[item['symbol']] = float(item['markPrice'])
        return px_map

    def fetch_pairs_info(self):
        pass  ##kraken不需要contractsize

    def spot_request(self,api_key = '', secrect_key = '', method: str = "GET", path: str = "", query: dict | None = None, body: dict | None = None, environment: str = "") -> http.client.HTTPResponse:
        url = environment + path
        query_str = ""
        if query is not None and len(query) > 0:
            query_str = urllib.parse.urlencode(query)
            url += "?" + query_str
        nonce = ""
        if len(api_key) > 0:
            if body is None:
                body = {}
            nonce = body.get("nonce")
            if nonce is None:
                nonce = str(int(time.time() * 1000))
                body["nonce"] = nonce
        headers = {}
        body_str = ""
        if body is not None and len(body) > 0:
            body_str = json.dumps(body)
            headers["Content-Type"] = "application/json"
        if len(api_key) > 0:
            headers["API-Key"] = api_key
            headers["API-Sign"] = self.get_spot_signature(secrect_key, query_str+body_str, nonce, path)
        req = urllib.request.Request(
            method=method,
            url=url,
            data=body_str.encode(),
            headers=headers,
        )
        return urllib.request.urlopen(req)

    def future_request(self, api_key, secrect_key, method: str = "GET", path: str = "", query: dict | None = None, body: dict | None = None, nonce: str = "", environment: str = "") -> http.client.HTTPResponse:
        url = environment + path
        query_str = ""
        if query is not None and len(query) > 0:
            query_str = urllib.parse.urlencode(query)
            url += "?" + query_str
        body_str = ""
        if body is not None and len(body) > 0:
            body_str = urllib.parse.urlencode(body)
        headers = {}
        if len(api_key) > 0:
            headers["APIKey"] = api_key
            headers["Authent"] = self.get_future_signature(secrect_key, query_str+body_str, nonce, path)
            if len(nonce) > 0:
                headers["Nonce"] = nonce
        req = urllib.request.Request(
            method=method,
            url=url,
            data=body_str.encode(),
            headers=headers,
        )
        return urllib.request.urlopen(req)

    def set_pos_mode(self):
        return 'succ'

    def set_leverage(self, symbol, leverage):
        return 'succ'

    def get_future_signature(self, secrect_key: str, data: str, nonce: str, path: str) -> str:
        return base64.b64encode(
            hmac.new(
                key=base64.b64decode(secrect_key),
                msg=hashlib.sha256(
                (data + nonce + path.removeprefix("/derivatives")).encode()
            ).digest(),
                digestmod=hashlib.sha512,
            ).digest()
        ).decode()

    def get_spot_signature(self, secrect_key, data: str, nonce: str, path: str) -> str:
        return base64.b64encode(
            hmac.new(
                key=base64.b64decode(secrect_key),
                msg=path.encode() + hashlib.sha256((nonce + data).encode()).digest(),
                digestmod=hashlib.sha512,
            ).digest()
        ).decode()


    def fetch_spot_balance(self):
        response = self.spot_request(
            api_key=self.spot_api_key,
            secrect_key=self.spot_secrect_key,
            method="POST",
            path="/0/private/Balance",
            environment="https://api.kraken.com",
        ).read().decode()
        #print(response)
        resp = json.loads(response)
        bal = Balance()
        bal.currency = 'USDT'
        bal.available = float(resp['result']['USDT'])
        bal.locked = 0.0
        bal.equity = bal.available
        return bal
    
    def fetch_future_balance(self):
        response = self.future_request(
            api_key = self.future_api_key,
            secrect_key = self.future_secrect_key,
            method = "GET",
            path = "/derivatives/api/v3/accounts",
            environment = "https://futures.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        #print(resp)
        bal = Balance()
        
        bal.currency = 'USDT'
        bal.available = float(resp['accounts']['flex']['availableMargin'])
        bal.locked = 0.0
        bal.equity = float(resp['accounts']['flex']['marginEquity'])
        
        #print(resp['accounts']['flex'])
        #print(bal)
        return bal
    
    # field spot, future
    def asset_transfer_inner(self, coin, from_field, to_field, amount):
        if from_field == 'spot':
            response = self.spot_request(
                method="POST",
                path="/0/private/WalletTransfer",
                body={
                    "asset": "USDT",
                    "from": "Spot Wallet",
                    "to": "Futures Wallet",
                    "amount": str(amount),
                },
                api_key=self.spot_api_key,
                secrect_key=self.spot_secrect_key,
                environment="https://api.kraken.com",
            ).read().decode()
            resp = json.loads(response)
            #print(resp)
            if resp['error'] : ##有错误
                return 1, resp
            else: ##没有错误
                return 0, resp
        else :
            response = self.future_request(
                api_key = self.future_api_key,
                secrect_key = self.future_secrect_key,
                method = "POST",
                body={
                    "currency": "USDT",
                    "amount": float(amount),
                    "sourceWallet": "flex",
                },
                path = "/derivatives/api/v3/withdrawal",
                environment = "https://futures.kraken.com",
            ).read().decode()
            resp = json.loads(response)
            if resp['result'] == 'success':
                return 0, resp
            else:
                return 1, resp
            
     ##提现
    def withdrawals(self, coin, to_exch, address, chain, amount):
        response = self.spot_request(
            method="POST",
            path="/0/private/Withdraw",
            body={
                "asset": coin,
                "key": address,
                "amount": str(amount),
            },
            api_key=self.spot_api_key,
            secrect_key=self.spot_secrect_key,
            environment="https://api.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        #print(resp)
        if resp.get("error"):
            return WithdrawalStatus(
                currency=coin, tx_id='0', withdraw_clt_id='0', 
                amount=amount, to_exch=to_exch, address=address, chain=chain, status=Status.FAIL, msg=resp)
        else: 
            return WithdrawalStatus(
                currency=coin, tx_id=resp['result'], withdraw_clt_id=resp['result'], 
                amount=amount, to_exch=to_exch, address=address, chain=chain, status=Status.PENDING, msg=resp)


    ##提现记录
    def query_withdrawals_record(self, withdraw_order_id):
        response = self.spot_request(
            method="POST",
            path="/0/private/WithdrawStatus",
            body={
                "asset": 'USDT',
            },
            api_key=self.spot_api_key,
            secrect_key=self.spot_secrect_key,
            environment="https://api.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        #print(resp)
        for item in resp['result']:
            if withdraw_order_id == item['refid']:
                if item['status'] == 'Success':
                    return Status.SUCC, item
                elif item['status'] in ('Initial', 'Pending', 'Settled'):
                    return Status.PENDING, item
                elif item['status'] == 'Failure':
                    return Status.FAIL, item
        if withdraw_order_id != None:
            return Status.FAIL, f'not found kraken withdrawals_record {withdraw_clt_id}'
        else:
            return Status.SUCC, 'no record'

    ##入金记录
    def query_desposite_record(self, tx_id):
        response = self.spot_request(
            method="POST",
            path="/0/private/DepositStatus",
            body={
                "asset": 'USDT',
            },
            api_key=self.spot_api_key,
            secrect_key=self.spot_secrect_key,
            environment="https://api.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        #print(resp)
        for item in resp['result']:
            if item['txid'] == tx_id:
                if item['status'] == 'Success':
                    return Status.SUCC, item
                elif item['status'] in ('Initial', 'Pending', 'Settled'):
                    return Status.PENDING, item
                elif item['status'] == 'Failure':
                    return Status.FAIL, item
        return Status.FAIL, f'not found kraken desposite_record {tx_id}'

     ##获取合约持仓
    def get_future_pos(self):
        positions = {}
        tickers = {}
        resp = requests.get('https://futures.kraken.com/derivatives/api/v3/tickers').json()
        for item in resp['tickers']:
            tickers[item['symbol']] = float(item['last']) if 'last' in item.keys() else 0.0
        response = self.future_request(
            method = "GET",
            path = "/derivatives/api/v3/openpositions",
            api_key=self.future_api_key,
            secrect_key=self.future_secrect_key,
            environment = "https://futures.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        for item in resp['openPositions']:
            size = float(item['size'])
            if size != 0:
                if item['side'] == 'short':
                    size = -float(item['size'])
                leverage = 10
                pos = Position(symbol = item['symbol'], size = size, entry_price = float(item['price']), liq_price = 0, leverage = leverage, now_price = tickers[item['symbol']])
                positions[item['symbol']] = pos
        return positions

    def fetch_open_order(self):
        response = self.future_request(
            method = "GET",
            path = "/derivatives/api/v3/openorders",
            api_key=self.future_api_key,
            secrect_key=self.future_secrect_key,
            environment = "https://futures.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        print(resp)
    
    def place_order(self):
        response = self.future_request(
            method="POST",
            path="/derivatives/api/v3/sendorder",
            body={
                "orderType": 'lmt',
                "symbol": 'PF_XBTUSD',
                "side": "sell",
                "size": "0.0001",
                "limitPrice": "80000",
            },
            api_key=self.future_api_key,
            secrect_key=self.future_secrect_key,
            environment="https://futures.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        print(resp)

    def cancel_all_order(self, symbol):
        response = self.future_request(
            method="POST",
            path="/derivatives/api/v3/cancelallorders",
            body={
                'symbol': symbol
            },
            api_key=self.future_api_key,
            secrect_key=self.future_secrect_key,
            environment="https://futures.kraken.com",
        ).read().decode()
        resp = json.loads(response)
        print(resp)

        
        