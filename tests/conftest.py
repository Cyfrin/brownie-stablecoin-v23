import pytest
from scripts.deploy_dsc import deploy_decentralized_stablecoin, deploy_dsc_engine
from scripts.helper_functions import get_account, deploy_mocks
from brownie import web3, MockWETH, MockV3Aggregator, accounts

WETH_INDEX = 0
WBTC_INDEX = 1

ONE_ETH = web3.toWei(1, "ether")
AMOUNT_COLLATERAL = web3.toWei(10, "ether")
AMOUNT_DSC_TO_MINT = web3.toWei(100, "ether")
COLLATERAL_TO_COVER = web3.toWei(20, "ether")
LIQUIDATION_THRESHOLD = 50


@pytest.fixture(scope="module")
def zero_address():
    return "0x0000000000000000000000000000000000000000"


@pytest.fixture(scope="function")
def account():
    return get_account()


@pytest.fixture(scope="function")
def liquidator():
    return accounts.add()


@pytest.fixture(scope="function")
def dsc():
    deploy_mocks()
    return deploy_decentralized_stablecoin()


@pytest.fixture(scope="function")
def dsce(dsc):
    return deploy_dsc_engine(dsc)


@pytest.fixture(scope="function")
def weth(dsc):
    return dsc.COLLATERAL_TOKENS(0)


@pytest.fixture(scope="function")
def dsce_with_collateral(dsce, account):
    weth = dsce.COLLATERAL_TOKENS(WETH_INDEX)
    mock_erc20 = MockWETH.at(weth)
    mock_erc20.mint(account, AMOUNT_COLLATERAL, {"from": account})
    mock_erc20.approve(dsce.address, AMOUNT_COLLATERAL, {"from": account})
    tx = dsce.deposit_collateral(weth, AMOUNT_COLLATERAL, {"from": account})
    tx.wait(1)
    return dsce


@pytest.fixture(scope="function")
def dsc_deposited_and_minted(dsce, account):
    weth = dsce.COLLATERAL_TOKENS(WETH_INDEX)
    mock_erc20 = MockWETH.at(weth)
    mock_erc20.mint(account, AMOUNT_COLLATERAL, {"from": account})
    mock_erc20.approve(dsce.address, AMOUNT_COLLATERAL, {"from": account})
    tx = dsce.deposit_collateral_and_mint_dsc(
        weth, AMOUNT_COLLATERAL, AMOUNT_DSC_TO_MINT, {"from": account}  #
    )
    tx.wait(1)
    return dsce


@pytest.fixture(scope="function")
def liquidated_dsce(dsc_deposited_and_minted, account, dsc, liquidator):
    weth = dsc_deposited_and_minted.COLLATERAL_TOKENS(WETH_INDEX)
    mock_weth = MockWETH.at(weth)
    eth_usd_price_feed = dsc_deposited_and_minted.token_address_to_price_feed(weth)

    eth_usd_updated_price = 18 * 10**8  # 1 ETH = $18
    mock_v3_aggregator = MockV3Aggregator.at(eth_usd_price_feed)
    mock_v3_aggregator.updateAnswer(eth_usd_updated_price)

    mock_weth.mint(liquidator, COLLATERAL_TO_COVER, {"from": account})
    mock_weth.approve(
        dsc_deposited_and_minted.address, COLLATERAL_TO_COVER, {"from": liquidator}
    )
    dsc_deposited_and_minted.deposit_collateral_and_mint_dsc(
        weth, COLLATERAL_TO_COVER, AMOUNT_DSC_TO_MINT, {"from": liquidator}
    )
    dsc.approve(
        dsc_deposited_and_minted.address, AMOUNT_DSC_TO_MINT, {"from": liquidator}
    )
    dsc_deposited_and_minted.liquidate(
        weth, account, AMOUNT_DSC_TO_MINT, {"from": liquidator}
    )
    return dsc_deposited_and_minted
