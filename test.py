from pymongo import MongoClient

mongo_clt = MongoClient('mongodb://admin:ceff12343@3.114.59.95:27179')

username = "teff_teff001"
client = username.split('_')[0]
name = username.split('_')[1]
# 选择数据库（此时还不会真正创建）
secrets_db = mongo_clt["Secrets_exch"][client]
deploy_db = mongo_clt["Strategy_deploy_exch"][client]
orch_db = mongo_clt["Strategy_orch_exch"][client]
# 选择集合

orch_doc = orch_db.find_one({"$and":[{"orch": True}, {"_id":{"$regex":f'{username}@exch_funding'}}]})
if orch_doc != None:
    deploy_doc = deploy_db.find_one({"_id":{"$regex":f'{username}@exch_funding'}})
    print(deploy_doc['secrets'])
    print(deploy_doc['transfer_config'])
    print(deploy_doc['pair_configs'])
    for item in deploy_doc['pair_configs']:
        print(item['master_pair'].split(':')[0], item['master_pair'].split(':')[2])
        print(item['slave_pair'].split(':')[0], item['slave_pair'].split(':')[2])
    '''
    for item in deploy_doc['secrets']:
        secret_doc = secrets_db.find_one({"_id":{"$regex":f'{item.split('/')[1]}'}})
        print(secret_doc)
        if secret_doc['exchange'] == 'kraken':
            spot_secret_doc = secrets_db.find_one({"_id":{"$regex":f'{secret_doc['_id'].split(":")[0] + ":spot"}'}})
            print(spot_secret_doc)
    '''
       
else:
    print("orch is none")



'''
gate_mgr = GateMgr(api_key = "9a13c50e604320bd0a2fe905d0808964", 
                       secrect_key = "d1e43148cfce36dcb869d2214851338441874edc12240126fe87d42e9b535a37", 
                       passphrase= "")
        kraken_mgr = KrakenMgr(future_api_key = "lptpBrv8o+FjaXm5FCV1CjdBS4/dlzM68teN2QBOexzKzAEvWlmQVODW", 
                            future_secrect_key = "EgH/cy89+FZMY5PYOtdF7pNJkaj7wR4APEX77dXPBgyMmZg7W9uMPVtjDA9e1pYeX2zmCYwVGzdeSytXrBv+H1De", 
                            future_passphrase = "",
                            spot_api_key='r7T8w6Q5jSXxvg/k4KP8ME5+WEs8P/pTNwcKbbo1+nDg/JmIF53isWJZ',
                            spot_secrect_key='XBg4BfZjPnQyIWQ/hbnCQ3M7X8jm9XofNwlp2m2e8RhsOUu1ummtIPGOvdNy5G/zrn6IeX+XDgjKX4ZuHGp7/A==',
                            spot_passphrase='')
        binance_mgr = BinanceMgr(api_key= "ObFNMbiFySvQapIuLmtx0ttUPeBfGXoUEVMTRky8ut6raHr9N9uDJXeslYrqjM7T",
                                secrect_key= "E5OA97KXT0ggGMmYbNEJl826pGl4qkP22coMZ5qNohTFxzrnBHmN0jaOwBXm1Ss6",
                                passphrase="")
        kucoin_mgr = KucoinMgr(api_key = "6894bd32c714e80001ef887a",
                            secrect_key = "6f307557-c4a5-4d54-a28c-da40124dc700",
                            passphrase = "Nfx921011.")
        okex_mgr = OkexMgr(api_key = '0aa1139e-ea07-41c4-ba65-29ecbb7ab37d',
                        secrect_key = 'FD5E84FB855BADA97EE85AC93E7E42C4',
                        passphrase = 'Ceff123456.')
        self.exch_mgr[Exchange.GATE] = gate_mgr
        self.exch_mgr[Exchange.KRAKEN] = kraken_mgr
        self.exch_mgr[Exchange.BINANCE] = binance_mgr
        self.exch_mgr[Exchange.KUCOIN] = kucoin_mgr
        self.exch_mgr[Exchange.OKEX] = okex_mgr

        self.exch_addr[Exchange.GATE] = {}
        self.exch_addr[Exchange.GATE][Chain.ERC20] = '0x37582bc9e75392CA3Af3E3bED112D8d2553D92eA'
        self.exch_addr[Exchange.GATE][Chain.TRC20] = 'TF1qnqmP4XWATYZrvnV2TWB7YCaUBQ53mS'

        self.exch_addr[Exchange.KRAKEN] = {}
        self.exch_addr[Exchange.KRAKEN][Chain.ERC20] = '0x39a5b3c00811a9dfc26f4d5f06483bf08eb31c9a'
        self.exch_addr[Exchange.KRAKEN][Chain.TRC20] = 'TQ2uG6jz9oAVGRzYxADsUHCwDnHeRK2QQG'

        self.exch_addr[Exchange.BINANCE] = {}
        self.exch_addr[Exchange.BINANCE][Chain.ERC20] = '0x6cb5f023918ad47ffc18cb1d504cec4a602eb272'
        self.exch_addr[Exchange.BINANCE][Chain.TRC20] = 'TQeuBCiEr86yZrW86wkgvYiHtYoibKD4Y8'

        self.exch_addr[Exchange.KUCOIN] = {}
        self.exch_addr[Exchange.KUCOIN][Chain.ERC20] = '0x816db4a2f0e5dcb9dd88179f03051fd8309156b2'
        self.exch_addr[Exchange.KUCOIN][Chain.TRC20] = 'TCDFZ35V9fjdXjUjCoDC8iH47QPwqvseSB'

        self.exch_addr[Exchange.OKEX] = {}
        self.exch_addr[Exchange.OKEX][Chain.ERC20] = '0x8eedba4e9dba420573d1d7f141c5f85e311dc782'
        self.exch_addr[Exchange.OKEX][Chain.TRC20] = 'TFcEPBGGEJbQdgA6ewAfrqSMpjp5UMx3cM'
        
'''