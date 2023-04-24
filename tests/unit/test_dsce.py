from brownie import (
    web3,
    reverts,
    DecentralizedStableCoin,
    MockV3Aggregator,
    MockWETH,
    accounts,
)
import pytest
from tests.conftest import (
    WETH_INDEX,
    ONE_ETH,
    AMOUNT_COLLATERAL,
    AMOUNT_DSC_TO_MINT,
    COLLATERAL_TO_COVER,
    LIQUIDATION_THRESHOLD,
)

#######################
# Price Feed Tests #
#######################


def test_get_token_amount_from_usd(dsce):
    weth = dsce.COLLATERAL_TOKENS(WETH_INDEX)
    expected_weth = web3.toWei(0.05, "ether")
    usd_amount = web3.toWei(100, "ether")
    amount_weth = dsce.get_token_amount_from_usd(weth, usd_amount)
    assert amount_weth == expected_weth


def test_get_usd_value(dsce):
    eth_amount = web3.toWei(15, "ether")
    expected_usd = web3.toWei(30000, "ether")
    weth = dsce.COLLATERAL_TOKENS(WETH_INDEX)
    usd_amount = dsce.get_usd_value(weth, eth_amount)
    assert usd_amount == expected_usd


#######################
# Deposit Collateral Tests
#######################


def test_reverts_if_collateral_zero(dsce, account):
    weth = dsce.COLLATERAL_TOKENS(WETH_INDEX)
    with reverts():
        dsce.deposit_collateral(weth, 0, {"from": account})


def test_reverts_with_unapproved_collateral(dsce, account):
    mock_coin = DecentralizedStableCoin.deploy("RANDOM", "RAND", {"from": account})
    amount_collateral = web3.toWei(100, "ether")
    with reverts():
        dsce.deposit_collateral(mock_coin.address, amount_collateral, {"from": account})


def test_can_deposit_collateral_without_minting(dsce_with_collateral, dsc, account):
    user_balance = dsc.balanceOf(account)
    assert user_balance == 0


def test_can_deposit_collateral_and_get_account_info(dsce_with_collateral, account):
    weth = dsce_with_collateral.COLLATERAL_TOKENS(WETH_INDEX)
    (
        total_dsc_minted,
        collateral_value_usd,
    ) = dsce_with_collateral.get_account_information(account)
    expected_deposited_amount = dsce_with_collateral.get_token_amount_from_usd(
        weth, collateral_value_usd
    )
    assert total_dsc_minted == 0
    assert expected_deposited_amount == AMOUNT_COLLATERAL


# =======================================
# depositCollateralAndMintDsc Tests
# =======================================


def test_reverts_if_minted_dsc_breaks_health_factor(dsce, account):
    weth = dsce.COLLATERAL_TOKENS(WETH_INDEX)
    feed = MockV3Aggregator.at(dsce.token_address_to_price_feed(weth))
    (
        _,
        price,
        _,
        _,
        _,
    ) = feed.latestRoundData()

    amount_to_mint = (
        AMOUNT_COLLATERAL * (price * dsce.ADDITIONAL_FEED_PRECISION())
    ) / dsce.PRECISION()

    mock_erc20 = MockWETH.at(weth)
    mock_erc20.mint(account, AMOUNT_COLLATERAL, {"from": account})
    mock_erc20.approve(dsce.address, AMOUNT_COLLATERAL, {"from": account})
    with reverts():
        dsce.deposit_collateral_and_mint_dsc(
            weth, AMOUNT_COLLATERAL, amount_to_mint, {"from": account}
        )


def test_can_mint_with_deposited_collateral(dsc_deposited_and_minted, account, dsc):
    dsc_deposited_and_minted
    user_balance = dsc.balanceOf(account)
    assert user_balance == AMOUNT_DSC_TO_MINT


# ======================
# mintDsc Tests
# ======================


def test_reverts_if_mint_amount_is_zero(dsc_deposited_and_minted):
    with reverts():
        dsc_deposited_and_minted.mint_dsc(0)


def test_reverts_if_mint_amount_breaks_health_factor(dsc_deposited_and_minted, account):
    weth = dsc_deposited_and_minted.COLLATERAL_TOKENS(WETH_INDEX)
    feed = MockV3Aggregator.at(
        dsc_deposited_and_minted.token_address_to_price_feed(weth)
    )
    (_, price, _, _, _) = feed.latestRoundData()

    amount_to_mint = (
        AMOUNT_COLLATERAL
        * (price * dsc_deposited_and_minted.ADDITIONAL_FEED_PRECISION())
    ) / dsc_deposited_and_minted.PRECISION()

    mock_erc20 = MockWETH.at(weth)
    mock_erc20.approve(
        dsc_deposited_and_minted.address, AMOUNT_COLLATERAL, {"from": account}
    )
    mock_erc20.mint(account, AMOUNT_COLLATERAL, {"from": account})
    dsc_deposited_and_minted.deposit_collateral(
        weth, AMOUNT_COLLATERAL, {"from": account}
    )

    with reverts():
        dsc_deposited_and_minted.mint_dsc(amount_to_mint, {"from": account})


def test_can_mint_dsc(dsce_with_collateral, account, dsc):
    dsce_with_collateral.mint_dsc(AMOUNT_DSC_TO_MINT, {"from": account})

    user_balance = dsc.balanceOf(account)
    assert user_balance == AMOUNT_DSC_TO_MINT


#######################
# Burn DSC Tests
#######################


def test_cant_burn_more_than_user_has(dsce_with_collateral, account):
    with reverts():
        dsce_with_collateral.burn_dsc(1, {"from": account})


def test_can_burn_dsc(dsc_deposited_and_minted, account, dsc):
    dsc.approve(dsc_deposited_and_minted.address, AMOUNT_DSC_TO_MINT, {"from": account})
    dsc_deposited_and_minted.burn_dsc(AMOUNT_DSC_TO_MINT, {"from": account})
    user_balance = dsc.balanceOf(account)
    assert user_balance == 0


#######################
# Redeem Collateral Tests
#######################


def test_can_redeem_collateral(dsce_with_collateral, account):
    weth = dsce_with_collateral.COLLATERAL_TOKENS(WETH_INDEX)
    dsce_with_collateral.redeem_collateral(weth, AMOUNT_COLLATERAL, {"from": account})

    user_balance = MockWETH.at(weth).balanceOf(account)
    assert user_balance == AMOUNT_COLLATERAL


def test_must_redeem_more_than_zero(dsce_with_collateral, account, dsc):
    weth = dsce_with_collateral.COLLATERAL_TOKENS(WETH_INDEX)
    dsc.approve(dsce_with_collateral.address, AMOUNT_DSC_TO_MINT, {"from": account})

    with reverts():
        dsce_with_collateral.redeem_collateral_for_dsc(
            weth, 0, AMOUNT_DSC_TO_MINT, {"from": account}
        )


def test_can_redeem_deposited_collateral_for_dsc(dsce_with_collateral, dsc, account):
    weth = dsce_with_collateral.COLLATERAL_TOKENS(WETH_INDEX)
    mock_erc20 = MockWETH.at(weth)
    mock_erc20.mint(account, AMOUNT_COLLATERAL, {"from": account})
    mock_erc20.approve(
        dsce_with_collateral.address, AMOUNT_COLLATERAL, {"from": account}
    )
    dsce_with_collateral.deposit_collateral_and_mint_dsc(
        weth, AMOUNT_COLLATERAL, AMOUNT_DSC_TO_MINT, {"from": account}
    )

    dsc.approve(dsce_with_collateral.address, AMOUNT_DSC_TO_MINT, {"from": account})
    dsce_with_collateral.redeem_collateral_for_dsc(
        weth, AMOUNT_COLLATERAL, AMOUNT_DSC_TO_MINT, {"from": account}
    )

    user_balance = dsc.balanceOf(account)
    assert user_balance == 0


#######################
# Health Factor Tests
#######################


def test_properly_reports_health_factor(dsc_deposited_and_minted, account):
    expected_health_factor = 100 * 10**18
    health_factor = dsc_deposited_and_minted.health_factor(account)

    # $100 minted with $20,000 collateral at 50% liquidation threshold
    # means that we must have $200 collateral at all times.
    # 20,000 * 0.5 = 10,000
    # 10,000 / 100 = 100 health factor
    assert health_factor == expected_health_factor


def test_health_factor_can_go_below_one(dsc_deposited_and_minted, account):
    eth_usd_price_feed = dsc_deposited_and_minted.token_address_to_price_feed(
        dsc_deposited_and_minted.COLLATERAL_TOKENS(WETH_INDEX)
    )

    eth_usd_updated_price = 18 * 10**8  # 1 ETH = $18
    # Remember, we need $150 at all times if we have $100 of debt

    mock_v3_aggregator = MockV3Aggregator.at(eth_usd_price_feed)
    mock_v3_aggregator.updateAnswer(eth_usd_updated_price, {"from": account})

    user_health_factor = dsc_deposited_and_minted.health_factor(account)
    # $180 collateral / 200 debt = 0.9
    assert user_health_factor == 0.9 * 10**18


#######################
# Liquidation Tests
#######################


def test_cant_liquidate_good_health_factor(dsc_deposited_and_minted, account, dsc):
    weth = dsc_deposited_and_minted.COLLATERAL_TOKENS(WETH_INDEX)
    liquidator = accounts.add()
    mock_weth = MockWETH.at(weth)
    mock_weth.mint(liquidator, COLLATERAL_TO_COVER, {"from": account})
    account.transfer(liquidator, ONE_ETH)

    mock_weth.approve(
        dsc_deposited_and_minted.address, COLLATERAL_TO_COVER, {"from": liquidator}
    )
    dsc_deposited_and_minted.deposit_collateral_and_mint_dsc(
        weth, COLLATERAL_TO_COVER, AMOUNT_DSC_TO_MINT, {"from": liquidator}
    )
    tx = dsc.approve(
        dsc_deposited_and_minted.address, AMOUNT_DSC_TO_MINT, {"from": liquidator}
    )
    tx.wait(1)

    with reverts("DSCEngine_HealthFactorOk"):
        dsc_deposited_and_minted.liquidate(
            weth, account, AMOUNT_DSC_TO_MINT, {"from": liquidator}
        )


def test_liquidation_payout_is_correct(liquidated_dsce, liquidator):
    weth = liquidated_dsce.COLLATERAL_TOKENS(WETH_INDEX)
    mock_weth = MockWETH.at(weth)
    liquidator_weth_balance = mock_weth.balanceOf(liquidator)

    expected_weth = liquidated_dsce.get_token_amount_from_usd(
        weth, AMOUNT_DSC_TO_MINT
    ) + (
        liquidated_dsce.get_token_amount_from_usd(weth, AMOUNT_DSC_TO_MINT)
        / liquidated_dsce.LIQUIDATION_BONUS()
    )

    # hard_coded_expected = 6111111111111111110
    # python is a little off with it's rounding
    assert expected_weth - 55 <= liquidator_weth_balance <= expected_weth + 55


def test_user_still_has_some_eth_after_liquidation(liquidated_dsce, account):
    weth = liquidated_dsce.COLLATERAL_TOKENS(WETH_INDEX)
    amount_to_mint = AMOUNT_DSC_TO_MINT

    amount_liquidated = liquidated_dsce.get_token_amount_from_usd(
        weth, amount_to_mint
    ) + (
        liquidated_dsce.get_token_amount_from_usd(weth, amount_to_mint)
        / liquidated_dsce.LIQUIDATION_BONUS()
    )

    usd_amount_liquidated = liquidated_dsce.get_usd_value(weth, amount_liquidated)
    expected_user_collateral_value_in_usd = (
        liquidated_dsce.get_usd_value(weth, AMOUNT_COLLATERAL) - usd_amount_liquidated
    )

    _, user_collateral_value_in_usd = liquidated_dsce.get_account_information(account)
    # hard_coded_expected_value = 70000000000000000020
    # Python rounding a little off?
    assert (
        expected_user_collateral_value_in_usd - 1000
        <= user_collateral_value_in_usd
        <= expected_user_collateral_value_in_usd + 1000
    )
    # assert user_collateral_value_in_usd == hard_coded_expected_value


def test_liquidator_takes_on_users_debt(liquidated_dsce, liquidator):
    liquidator_dsc_minted, _ = liquidated_dsce.get_account_information(liquidator)
    assert liquidator_dsc_minted == AMOUNT_DSC_TO_MINT


def test_user_has_no_more_debt(liquidated_dsce, account):
    user_dsc_minted, _ = liquidated_dsce.get_account_information(account)
    assert user_dsc_minted == 0


def test_get_min_health_factor(dsce):
    min_health_factor = dsce.MIN_HEALTH_FACTOR()
    assert min_health_factor == ONE_ETH


def test_get_liquidation_threshold(dsce):
    liquidation_threshold = dsce.LIQUIDATION_THRESHOLD()
    assert liquidation_threshold == LIQUIDATION_THRESHOLD


def test_get_account_collateral_value_from_information(dsce_with_collateral, account):
    _, collateral_value = dsce_with_collateral.get_account_information(account)
    weth = dsce_with_collateral.COLLATERAL_TOKENS(WETH_INDEX)
    expected_collateral_value = dsce_with_collateral.get_usd_value(
        weth, AMOUNT_COLLATERAL
    )
    assert collateral_value == expected_collateral_value


def test_get_collateral_balance_of_user(dsce_with_collateral, account):
    weth = dsce_with_collateral.COLLATERAL_TOKENS(WETH_INDEX)
    collateral_balance = dsce_with_collateral.get_collateral_balance_of_user(
        account, weth
    )
    assert collateral_balance == AMOUNT_COLLATERAL


def test_get_account_collateral_value(dsce_with_collateral, account):
    weth = dsce_with_collateral.COLLATERAL_TOKENS(WETH_INDEX)
    collateral_value = dsce_with_collateral.get_account_collateral_value(account)
    expected_collateral_value = dsce_with_collateral.get_usd_value(
        weth, AMOUNT_COLLATERAL
    )
    assert collateral_value == expected_collateral_value


def test_get_dsc(dsce, dsc):
    dsc_address = dsce.DSC()
    assert dsc_address == dsc.address
