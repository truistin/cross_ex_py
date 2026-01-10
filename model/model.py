import simplejson
from enum import Enum

class Balance:
    currency: str
    available: float
    locked: float
    equity: float

    def __init__(self, currynce = 'USDT', available = 0.0, locked = 0.0, equity = 0.0):
        self.currency = currynce
        self.available = float(available)
        self.locked = float(locked)
        self.equity = float(equity)

    def stringify(self):
        return simplejson.dumps(self.__dict__)
    
    def __str__(self):
        return self.stringify()

class Exchange(str, Enum):
    BINANCE = 'binance'
    OKEX = 'okex'
    GATE = 'gate'
    KUCOIN = 'kucoin'
    KRAKEN = 'kraken'

def format_symbol(exchange: Exchange, symbol: str) -> str:
    """
    输入:  INIT/USDT
    输出:
      BINANCE -> INITUSDT
      GATE    -> INIT_USDT
      OKX     -> INIT-USDT-SWAP
    """
    if exchange == Exchange.BINANCE:
        return symbol.replace("/", "")
    elif exchange == Exchange.GATE:
        return symbol.replace("/", "_")
    elif exchange == Exchange.OKEX:
        return symbol.replace("/", "-") + "SWAP"
    elif exchange == Exchange.KUCOIN:
        if symbol == 'BTC/USDT':
            symbol = 'XBTUSDTM'
        else:
            symbol = symbol.replace('/', '') + 'M'
        return symbol
    elif exchange == Exchange.KRAKEN:
        if symbol == "BTC/USDT":
            return "PF_XBTUSD"
        else:
            return "PF_" + symbol.replace("/", "")[:-1]
    else:
        raise ValueError(f"unsupported exchange: {exchange}")

class Chain(str, Enum):
    TRC20 = 'trc20'
    ERC20 = 'erc20'

class NeedTransfer(str, Enum):
    NEW = 'new'
    PENDING = 'pending'

class Status(str, Enum):
    SUCC = 'SUCC' ##链上划转成功
    CANCEL = 'CANCEL' ##链上划转取消成功
    FAIL = 'FAIL'  ##链上划转失败
    PENDING = 'PENDING'  ##链上划转中

class WithdrawalStatus:
    currency: str
    amount: str
    withdraw_id: str
    withdraw_clt_id: str
    status: Status
    to_exch: Exchange
    address: str
    chain: str
    msg: str

    def __init__(self, currency, tx_id, withdraw_clt_id, to_exch, status, amount, address, chain, msg):
        self.currency = currency
        self.tx_id = tx_id
        self.withdraw_clt_id = withdraw_clt_id
        self.status = status
        self.amount = amount
        self.address = address
        self.chain = chain
        self.to_exch = to_exch
        self.msg = msg

    def stringify(self):
        return simplejson.dumps(self.__dict__)
    
    def __str__(self):
        return self.stringify()
    
class Position:
    symbol: str
    size: float #仓位，size>0 做多， size<0 做空
    entry_price: float #开仓均价
    liq_price: float #爆仓价格
    leverage: float #杠杆
    now_price: float #当前价格

    def __init__(self, symbol='', size = 0.0, entry_price = 0.0, liq_price= 0.0, leverage = 1.0, now_price = 0.0):
        self.symbol = symbol
        self.size = float(size)
        self.entry_price = float(entry_price)
        self.liq_price = float(liq_price)
        self.leverage = float(leverage)
        self.now_price = float(now_price)

    def __str__(self):
        return f"Position({self.symbol}, size={self.size}, entry={self.entry_price}), leverage={self.leverage}, now_price={self.now_price}"
    