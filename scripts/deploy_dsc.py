#!/usr/bin/python3
from brownie import DecentralizedStableCoin, DSCEngine, network
from scripts.helper_functions import get_account, get_contract

NAME = "DecentralizedStableCoin"
SYMBOL = "DSC"


def deploy_decentralized_stablecoin() -> DecentralizedStableCoin:
    account = get_account()
    print(f"On network {network.show_active()}")
    dsc = DecentralizedStableCoin.deploy(
        NAME,
        SYMBOL,
        {"from": account},
    )

    # Poor vyper :(
    # if is_verifiable_contract():
    #     dsc.tx.wait(BLOCK_CONFIRMATIONS_FOR_VERIFICATION)
    #     DecentralizedStableCoin.publish_source(dsc)

    return dsc


def deploy_dsc_engine(dsc=None) -> DSCEngine:
    if not dsc:
        dsc = deploy_decentralized_stablecoin()
    account = get_account()
    weth_usd_price_feed_address = get_contract("weth_usd_price_feed").address
    wbtc_usd_price_feed_address = get_contract("wbtc_usd_price_feed").address
    weth = get_contract("weth").address
    wbtc = get_contract("wbtc").address

    token_addresses = [weth, wbtc]
    price_feed_addresses = [weth_usd_price_feed_address, wbtc_usd_price_feed_address]

    dsc_engine = DSCEngine.deploy(
        token_addresses, price_feed_addresses, dsc.address, {"from": account}
    )
    print(f"Deployed DSC Engine to {dsc_engine.address}")
    tx = dsc.set_minter(dsc_engine.address, {"from": account})
    tx.wait(1)
    return dsc_engine


def main():
    dsc = deploy_decentralized_stablecoin()
    deploy_dsc_engine(dsc)
