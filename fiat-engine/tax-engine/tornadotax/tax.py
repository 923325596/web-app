#Copyright (c) 2018 Daniel B. Grunberg
#
#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License version 3 as published by
#the Free Software Foundation.
#
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.
#
#You should have received a copy of the GNU Affero General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''
Crypto tax calculations - tax engine
usage:
x=Tax()
for tx in list_of_transactions_in_time_order:
    x.addtx(tx_object)
x.get_gains()    # This is from sales and/or trades
x.get_income()   # this is from MINE transactions
x.get_basis()    # remaining basis at any point of all tax lots
x.get_exceptions()  # list of coins that had no prior entry/DEP to match up to
We track coins by account+sym.  If 2 accounts are at bittrex, for example, then they
should be given different account names

For now, USD is the tracked quantity - upgrade later to make more general
basis is tracked by lots.  
account+'~'+sym => a list of [date_acquired, quantity, gross, fee, basis (total, in USD) ]
This list will be a dict with keys:  date, quantity, basis
This basis is updated on each transaction
gains/losses are generated on any sale or a buy with a non-USD symopp.

Attributes of tx
================
dt
account:
txid
action: DEP,BUY,SELL,WD,INIT,MINE  #INIT is a start (basically like a DEP), gross gives basis
pair:   trading pair from the exchange, not used for anything here
sym:    the symbol that BUY/SELL/MINE/INIT applies to.  Never fiat unless DEP/WD
symopp: the opposing symbol.  Could be fiat, e.g. USD.  for INIT, should be fiat
gross:  in symopp, total price paid or received. (not used for MINE)
quantity: number of sym
fee:    in symopp (not used for MINE)
address:for WD transactions.  Can be an account name or bitcoin address, etc.
note:   some text taken from the file

keys of taxlots dict entry
(key=account+'~'+sym)
==========================
dt
quantity
gross      # must be in fiat
fee        # must be in fiat

keys of gains list
==================
dt_acquired
dt_sold
descr         # description of property
quantity
proceeds
fee_sale
basis
fee_purchase

keys of income list (mining)
===================
dt
descr
quantity
gross    # fiat
fee      # fiat


keys of exception list
=====================
Reference IRS Pub 544 Sales of Assets, Pub 551 Basis
RULES:
In a trade:
Amounts realized=total received (money + FMV of property)
basis=basis of all property given

Basis:
basis of property received in a trade = FMV at time of receipt

EXAMPLE A:
sym=BTC, symopp=ETH
sell 1.2 BTC-ETH at price of 10.5 ETH/BTC with a fee of 0.10 ETC.


change after trade:     -1.2 BTC
                      +10.5-0.10 ETH

This has tax consequences: 
  sale: amount realized= (10.5-0.10)*for current_ETH_Price
        basis=basis of 1.2BTC
  new tax lot ETH of (10.5-0.10) ETH at (10.5 - 0.10) ETH*current_ETH_Price

EXAMPLE B:
sym=BTC, symopp=ETH
buy 1.2 BTC-ETH at price of 10.5 ETH/BTC with a fee of 0.10 ETC.

change after trade:     +1.2 BTC
                      -(10.5+0.10) ETH

This has tax consequences:
  sale: amount realized=1.2BTC*current_BTC_price, fee=0; 
        basis=basis of (10.5+0.10) ETH shares
  new tax lot BTC of 1.2 BTC with basis = 1.2BTC*current_BTC_price

NOTES:
should the tx input to addtx be a single object type, or different types based on the tx:
TRADE (BUY/SELL), CREDIT (DEP/WD), MINE, INIT ?

Currently implemented as no like-kind exchange. This might have been allowed in 2017,
would need to modify to handle that case as well - probably in the creation of Tax object.
There seems to be conflicting advice on whether like-kind exchange applied in 2017.  I think
disallowed for 2018 and forward.

We could replace addr in Tax() creation as a function that returns account for a given address.
For demo/testing, could read these things from a input text file

TODO:
On a transfer, how to treat the fee involved?  
Is it a sale at a cap gain?  YES
And does it change the basis of the transferred Crypto? NO.  
Probably a misc expense item (we will need a new list)


'''
import os
import datetime
from . import utils
#This object represents a transaction, see above for attributes
class Tx:
    def __str__(self):
        #for printing out the attributes
        return str(self.__dict__)

    @property
    def label(self):
        return self.account+'~'+self.sym

    def new_label(self, account):
        #The label to use if account changed
        return account+'~'+self.sym
    
class Tax():
    '''
    tax engine class
    Note that we will decompose a BUY or SELL action into 2 trades involving fiat if they
    do not involved fiat originally
    '''
    @staticmethod
    def label(account, sym):
        return account+'~'+sym

    @staticmethod
    def price_cb(sym, date):
        #dummy default function
        if sym=='BTC':
            return 6000
        elif sym=='ETH':
            return 600
        else:
            return 1.0
    
    #Public functions
    def __init__(self, year=1900,price_cb=None, addr=None):
        #Create a new Tax object.  year is default year used for sales of assets with unknown
        #acquisition dates (Jan 1 of that year will be used)
        #price_cb is a function price_cb(sym,date) that returns a price
        #addr is dict of address=>account (e.g. BTC address to which account that means)
        if price_cb is not None:
            #override our default function with the one provided
            self.price_cb=price_cb 
            
        self.taxlots={}  # label=>list of {date,quantity,gross,fee}
        self.gains=[]    # list (time order) of {dt_acquired,dt_sold,quantity,
                         #    proceeds,fee_sale,basis,fee_purchase
        self.income=[]
        self.year=year
        self.addr=addr
        
    def get_gains(self):
        return self.gains

    def get_taxlots(self):
        return self.taxlots

    def get_income(self):
        return self.income
    
    def total_proceeds(self):
        return sum([x['proceeds'] for x in self.gains])

    def total_basis(self):
        return sum([x['basis'] for x in self.gains])

    def total_taxlots(self):
        #return list of total quantity, gross, fee
        quantity=0
        gross=0
        fee=0
        for tl,v in self.taxlots.items():
            for x in v:
                quantity+=x['quantity']
                gross+=x['gross']
                fee+=x['fee']
        return [quantity, gross, fee]
            
    def addtx(self,tx):
        #add the transaction and compute gain/loss
        #adjust the basis of remaining stocks
        if tx.action in ['BUY', 'SELL']:
            self.buysell(tx)
        elif tx.action=='DEP':
            self.dep(tx)
        elif tx.action=='WD':
            self.wd(tx)
        elif tx.action=='INIT':
            self.init(tx)
        elif tx.action=='MINE':
            self.mine(tx)
        else:
            raise ValueError('Unknown action: {}'.format(tx.action))
    
    def buysell(self,tx):
        if tx.symopp=='USD':
            #Just 1 transaction to do
            if tx.action=='BUY':
                self.buy(tx.account,tx.dt,tx.sym,tx.quantity,tx.gross,tx.fee)
            elif tx.action=='SELL':
                self.sell(tx.account,tx.dt,tx.sym,tx.quantity,tx.gross,tx.fee)
        else:
            #we need 2 transactions
            price_sym=self.price_cb(sym=tx.sym, date=tx.dt)
            price_symopp=self.price_cb(sym=tx.symopp, date=tx.dt)
            if tx.action=='BUY':
                gross=tx.quantity*price_sym
                self.sell(tx.account,tx.dt,tx.symopp,tx.gross+tx.fee,tx.quantity*price_sym,0)
                self.buy(tx.account,tx.dt,tx.sym,tx.quantity,tx.quantity*price_sym,0)
            elif tx.action=='SELL':
                self.sell(tx.account,tx.dt,tx.sym,tx.quantity,(tx.gross-tx.fee)*price_symopp,0)
                self.buy(tx.account,tx.dt,tx.symopp,tx.gross-tx.fee,price_symopp*(tx.gross-tx.fee),0)
        
    #Private functions
    def buy(self,account,dt,sym,quantity,gross,fee):
        #buy a single symbol for fiat
        #No gains, just add to basis tax lots
        new_taxlot={'dt': dt, 'quantity':quantity, 'gross':gross, 'fee':fee }
        self.taxlots.setdefault(self.label(account,sym), []).append(new_taxlot)

    def sell(self,account,dt,sym,quantity,gross,fee):
        #sell a single symbol for fiat
        #find matching tax lots in FIFO order
        #add to self.gains, remove matching taxlots, add exceptions
        label=self.label(account,sym)
        #make sure at least an empty list of taxlots, then sort them by dt
        taxlots=self.taxlots.setdefault(label, [])
        print('taxlots={}'.format(taxlots))
        taxlots=sorted(taxlots, key=lambda x: x['dt'])
        remaining_quantity=quantity
        while remaining_quantity > 0:
            #if remaining amount cannot be found in taxlots, then give it a zero basis and
            #print a warning
            #need to sort by date to do FIFO
            #NOTE: maybe use .sort() which sorts in place?
            print('\nLOOP taxlots remaining:')
            utils.print_taxlots(taxlots,label)
            if len(taxlots)<1:
                #nothing left
                gain={'dt_acquired':datetime.datetime(self.year,1,1),
                      'dt_sold':dt,
                      'descr':label,
                      'quantity':remaining_quantity,
                      'proceeds':remaining_quantity/quantity*gross,
                      'fee_sale':remaining_quantity/quantity*fee,
                      'basis':0,
                      'fee_purchase':0}
                self.gains.append(gain)
                print('\nWARNING there were no tax lots for: {}'.format(gain))
                break
            taxlot=taxlots[0]   # consider the first one (FIFO)
            use=min(taxlot['quantity'], remaining_quantity)
            fract=use/taxlot['quantity']  # fraction of this taxlot
            gain={'dt_acquired':taxlot['dt'],
                  'dt_sold':dt,
                  'descr':label,
                  'quantity':use,
                  'proceeds':use/quantity*gross,
                  'fee_sale':use/quantity*fee,
                  'basis':fract*taxlot['gross'],
                  'fee_purchase':fract*taxlot['fee']}
            self.gains.append(gain)
            if use >= taxlot['quantity']:
                #use up all of the first tax lot
                remaining_quantity -= use
                del taxlots[0]
                #loop again
            else:
                #finished up use on this first taxlot
                quantity -= use
                taxlot['quantity'] -= use  # modify the first taxlot
                taxlot['gross']*=1-fract
                taxlot['fee']*=1-fract
                break
        
    def wd(self,tx):
        #a withdrawal removes taxlot(s) and moves them to a different account
        #Note that we have to use FIFO
        if self.addr is None or tx.address not in self.addr:
            print('ERROR address {} not in addr, not able to process wd {}'.format(tx.address,tx))
            return
        new_account=self.addr[tx.address]
        label=self.label(tx.account,tx.sym)
        new_label=self.label(new_account,tx.sym)
        quantity=tx.quantity
        taxlots=self.taxlots[label]
        #need to sort by date to do FIFO
        #NOTE: maybe use .sort() which sorts in place?
        taxlots=sorted(taxlots, key=lambda x: x['dt'])
        self.taxlots[label]=taxlots  # replace with sorted one
        print('WD: sorted taxlots: {}'.format(taxlots))
        if new_label not in self.taxlots:
            self.taxlots[new_label]=[]
        while quantity > 0:
            taxlot=taxlots[0]   # consider the first one
            use=min(taxlot['quantity'], quantity)
            if use >= taxlot['quantity']:
                #use up all of the first tax lot
                quantity -= taxlot['quantity']
                #Move to new one
                self.taxlots[new_label].append(taxlots[0])
                del taxlots[0]
                #loop again
            else:
                #finished up use on this first taxlot
                quantity -= use
                gross=use/taxlot['quantity']*taxlot['gross']
                fee=use/taxlot['quantity']*taxlot['fee']
                self.taxlots[new_label].append({'dt':taxlot['dt'],'quantity':use,'gross':gross,'fee':fee})
                taxlot['quantity'] -= use
                break
        print('WD finished. From {} to {} taxlots:'.format(label,new_label))
        utils.print_taxlots(self.taxlots[new_label], new_label)

    def dep(self,tx):
        #a deposit should match up to a withdrawal somewhere. Otherwise we won't
        #know the basis of it.
        if tx.sym=='USD':
            print('USD Deposit')
        else:
            print('ignoring a crypto deposit for now, should be a matching wd')
        #TODO: check that there is a matching wd (note that it might occur later in dt order,
        #due to imperfect dt ordering
        return
        
    def init(self,tx):
        #create a new taxlot
        label=self.label(tx.account,tx.sym)
        new_taxlot={'dt': tx.dt, 'quantity':tx.quantity, 'gross':tx.gross, 'fee':tx.fee }
        self.taxlots.setdefault(label, []).append(new_taxlot)        
    
    def mine(self,tx):
        #Mining income - add to self.income and self.taxlots
        #Uses market price on that dt, not income gross/fee of transaction
        label=self.label(tx.account,tx.sym)
        inc={'dt':tx.dt,
             'descr': label,
             'quantity': tx.quantity,
             'gross': tx.quantity+self.price_cb(tx.sym, tx.dt),
             'fee':0
        }
        self.income.append(inc)
        #taxlot
        new_taxlot={'dt': tx.dt, 'quantity':tx.quantity, 'gross':inc['gross'], 'fee':inc['fee'] }
        self.taxlots.setdefault(label, []).append(new_taxlot)

    
