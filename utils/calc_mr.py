def calc_margin( position_value, leverage):
        IM = abs(position_value) / leverage
        return IM

def calc_account_IM(positions):
    # positions: list of dict {value, leverage}
    return sum(calc_margin(p["value"], p["leverage"]) for p in positions)

def calc_SM(IM, safety_factor=2): # 2 10个点转账， 5个点 平仓
    return IM * safety_factor

def calc_MSR(equity, SM):
    return equity / SM