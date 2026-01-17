import hmac
import hashlib
import requests
import json
import time
import urllib.parse
from model.model import Balance, WithdrawalStatus, Status, Position, Chain

class GateMgr():
    api_key: str
    secrect_key: str
    passphrase: str
    pairs_info: dict

    def __init__(self, api_key, secrect_key, passphrase = ''):
        self.api_key = api_key
        self.secrect_key = secrect_key
        self.passphrase = passphrase
        self.pairs_info = {}
    
    def fetch_now_px(self):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/futures/usdt/contracts'
        query_param = ''
        r = requests.request('GET', host + prefix + url, headers=headers).json()
        px_map = {}
        for item in r:
            px_map[item['name']] = float(item['last_price'])
        return px_map

    def fetch_pairs_info(self):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/futures/usdt/contracts'
        query_param = ''
        r = requests.request('GET', host + prefix + url, headers=headers).json()
        #print(r)
        for item in r:
            self.pairs_info[item['name']] = float(item['quanto_multiplier'])

    def gen_sign(self, method, url, query_string = None, body_string = None):
        t = time.time()
        m = hashlib.sha512()
        m.update((body_string or "").encode('utf-8'))
        hashed_payload = m.hexdigest()
        s = '%s\n%s\n%s\n%s\n%s' % (method, url, query_string or "", hashed_payload, t)
        sign = hmac.new(self.secrect_key.encode('utf-8'), s.encode('utf-8'), hashlib.sha512).hexdigest()
        return {'KEY': self.api_key, 'Timestamp': str(t), 'SIGN': sign}
    
    def set_pos_mode(self):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/futures/usdt/dual_mode'
        query_param = 'dual_mode=false'  # false: 单项持仓, true: 双向持仓
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('POST', prefix + url, query_param)
        headers.update(sign_headers)
        r = requests.request('POST', host + prefix + url + "?" + query_param, headers=headers)
        print(r.json())


    def set_leverage(self, symbol, leverage):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = f'/futures/usdt/positions/{symbol}/leverage'
        query_param = f'leverage=0&cross_leverage_limit={leverage}'
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('POST', prefix + url, query_param)
        headers.update(sign_headers)
        r = requests.request('POST', host + prefix + url + "?" + query_param, headers=headers).json()
        return r

    def fetch_spot_balance(self):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/spot/accounts'
        query_param = ''
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('GET', prefix + url, query_param)
        headers.update(sign_headers)
        r = requests.request('GET', host + prefix + url, headers=headers).json()
        #print(r)
        bal = Balance()
        for item in r:
            if item['currency'] == 'USDT':
                bal.currency = item['currency']
                bal.available = float(item['available'])
                bal.locked = float(item['locked'])
                bal.equity = float(item['available'])
                return bal
        #print(bal)
        return bal
    
    def fetch_future_balance(self):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/futures/usdt/accounts'
        query_param = ''
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('GET', prefix + url, query_param)
        headers.update(sign_headers)
        r = requests.request('GET', host + prefix + url, headers=headers).json()
        #print(r)
        bal = Balance()
        bal.currency = r['currency']
        bal.available = float(r['cross_available'])
        bal.locked = 0.0
        bal.equity = float(r['total']) + float(r['unrealised_pnl'])
        #print(bal)
        return bal

    # field: spot futures
    def asset_transfer_inner(self, coin, from_field, to_field, amount):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/wallet/transfers'
        query_param = ''
        body = {}
        body['currency'] = coin.upper()
        body['from'] = from_field
        body['to'] = to_field
        body['amount'] = str(round(amount, 2))
        body['settle'] = 'USDT'
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('POST', prefix + url, query_param, json.dumps(body))
        headers.update(sign_headers)
        r = requests.request('POST', host + prefix + url, headers=headers, data=json.dumps(body)).json()
        #print(r)
        if 'tx_id' in r.keys(): ##成功
            return 0, r
        else:
            return 1, r

    ##提现
    def withdrawals(self, coin, to_exch, address, chain, amount):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/withdrawals'
        query_param = ''
        body = {}
        body['withdraw_order_id'] = 'gate_withdrawals_' + str(int(time.time() * 1000))
        body['currency'] = coin
        body['address'] = address
        if chain == Chain.ERC20:
            body['chain'] = 'ETH'
        elif chain == Chain.TRC20:
            body['chain'] = 'TRX'
        body['amount'] = amount
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('POST', prefix + url, query_param, json.dumps(body))
        headers.update(sign_headers)
        r = requests.request('POST', host + prefix + url, headers=headers, data=json.dumps(body)).json()
        print(r)
        if 'label' in r.keys():
            status = Status.FAIL
            return WithdrawalStatus(
                currency=coin, tx_id='0', withdraw_clt_id=body['withdraw_order_id'], 
                amount=amount, to_exch= to_exch, address=address, chain=chain, status=status, msg=r)
        elif r['status'] == 'CANCEL':
            status = Status.CANCEL
        elif r['status'] in ('FAIL', 'INVALID'):
            status = Status.FAIL
        else:
            status = Status.PENDING
        return WithdrawalStatus(
                currency=r['currency'], tx_id=None, withdraw_clt_id=r['withdraw_order_id'], 
                amount=r['amount'], to_exch= to_exch, address=r['address'], chain=r['chain'], status=status, msg=r['status'])


    ##提现记录
    def query_withdrawals_record(self, withdraw_clt_id):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/wallet/withdrawals'
        query_param = {}
        query_param['currency'] = 'USDT'
        query_param['withdraw_order_id'] = withdraw_clt_id
        query_string = urllib.parse.urlencode(query_param)
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('GET', prefix + url, query_string)
        headers.update(sign_headers)
        r = requests.request('GET', host + prefix + url + "?" + query_string, headers=headers).json()
        print(r)
        if len(r) == 0:
            return Status.SUCC, 'no record'
        #print(r)
        if r[0]['block_number'] == '':
            block_number = 0
        else:
            block_number = int(r[0]['block_number'])
        if (r[0]['status'] == 'DONE' and block_number > 0): ##跨所转出成功
            return Status.SUCC, r[0]
        elif r[0]['status'] == 'CANCEL' or r[0]['status'] == 'FAIL' or r[0]['status'] == 'REJECT':
            return Status.FAIL, r[0]['status']
        return Status.PENDING, r[0]['status']

    ##入金记录
    def query_desposite_record(self, tx_id):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/wallet/deposits'
        query_param = {}
        query_param['currency'] = 'USDT'
        query_param['limit'] = 500
        query_string = urllib.parse.urlencode(query_param)
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('GET', prefix + url, query_string)
        headers.update(sign_headers)
        r = requests.request('GET', host + prefix + url + "?" + query_string, headers=headers).json()
        print(r)
        for item in r:
            if item['txid'] == tx_id:
                if item['status'] == 'BLOCKED':
                    return Status.FAIL, f"拒绝充值({item['status']})"
                elif item['status'] == 'INVALID':
                    return Status.FAIL, f"无效数据({item['status']})"
                elif item['status'] == 'DEP_CREDITED':
                    return Status.PENDING, f"充值到账，提现未解锁({item['status']})"
                elif item['status'] == 'MANUAL':
                    return Status.PENDING, f"转人工审核({item['status']})"
                elif item['status'] == 'PEND':
                    return Status.PENDING, f"处理中({item['status']})"
                elif item['status'] == 'REVIEW':
                    return Status.PENDING, f"充值审核中(合规审查)({item['status']})"
                elif item['status'] == 'TRACK':
                    return Status.PENDING, f"跟踪确认数，等待给用户添加资金(现货)({item['status']})"
                elif item['status'] == 'DONE': #充值成功
                    return Status.SUCC, f"已经给账户增加资金({item['status']})"
        return Status.FAIL, f'not found deposite record, tx_id:{tx_id}'
    
    ##获取合约持仓
    def get_future_pos(self):
        positions = {}
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/futures/usdt/positions'
        query_param = ''
        # `gen_sign` 的实现参考认证一章
        sign_headers = self.gen_sign('GET', prefix + url, query_param)
        headers.update(sign_headers)
        r = requests.request('GET', host + prefix + url, headers=headers).json()
        #print(r)
        for item in r:
            if float(item['size']) != 0:
                print(item)
                pos = Position(symbol = item['contract'], size = float(item['size']) * float(self.pairs_info[item['contract']]), entry_price = float(item['entry_price']), liq_price = float(item['liq_price']), leverage = float(item['cross_leverage_limit']), now_price = float(item['mark_price']))
                positions[item['contract']] = pos
        return positions
    
    def get_chain_info(self):
        host = "https://api.gateio.ws"
        prefix = "/api/v4"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

        url = '/wallet/currency_chains'
        query_param = 'currency=USDT'
        r = requests.request('GET', host + prefix + url + "?" + query_param, headers=headers).json()
        #print(r)
        for item in r:
            print(item['chain'], item['name_cn'])

##/opt/homebrew/Caskroom/miniconda/base/bin/python3
if __name__ == "__main__":
    api_key = "9a13c50e604320bd0a2fe905d0808964"
    secrect_key = "d1e43148cfce36dcb869d2214851338441874edc12240126fe87d42e9b535a37"
    passphrase = ""
    '''
    gate_mgr = GateMgr(api_key, secrect_key, passphrase)
    gate_mgr.fetch_spot_balance()
    gate_mgr.fetch_future_balance()
    gate_mgr.asset_transfer_inner('usdt', 'spot', 'futures', 6.6121)
    '''
    gate_mgr.get_chain_info()