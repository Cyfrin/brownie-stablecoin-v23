# SPDX-License-Identifier: MIT
# @version 0.3.7
"""
@title DecentralizedStableCoin
@author Patrick Collins
@notice 
    Collateral: Exogenous
    Minting (Stability Mechanism): Decentralized (Algorithmic)
    Value (Relative Stability): Anchored (Pegged to USD)
    Collateral Type: Crypto
"""

from vyper.interfaces import ERC20
from interfaces import AggregatorV3Interface
from DecentralizedStableCoin import DecentralizedStableCoin

# Constants
LIQUIDATION_THRESHOLD: public(constant(uint256)) = 50
LIQUIDATION_BONUS: public(constant(uint256)) = 10
MIN_HEALTH_FACTOR: public(constant(uint256)) = 1 * (10 ** 18)
PRECISION: public(constant(uint256)) = 1 * (10 ** 18)
ADDITIONAL_FEED_PRECISION: public(constant(uint256)) = 1 * (10 ** 10)
FEED_PRECISION: public(constant(uint256)) = 1 * (10 ** 8)

# Immutables
DSC: public(immutable(DecentralizedStableCoin))
COLLATERAL_TOKENS: public(immutable(address[2]))

# Storage Variables
token_address_to_price_feed: public(HashMap[address, address])
user_to_token_address_to_amount_deposited: public(HashMap[address, HashMap[address, uint256]])
user_to_dsc_minted: public(HashMap[address, uint256])

event CollateralDeposited:
    user: indexed(address)
    amount: indexed(uint256)

event CollateralRedeemed:
    redeemed_from: indexed(address)
    amount_collateral: indexed(uint256)
    _from: address
    _to: address

@external
def __init__(token_addresses: address[2], price_feed_addresses: address[2], dsc_address: address):
    DSC = DecentralizedStableCoin(dsc_address)
    COLLATERAL_TOKENS = token_addresses
    # This is gas inefficient!
    self.token_address_to_price_feed[token_addresses[0]] = price_feed_addresses[0]
    self.token_address_to_price_feed[token_addresses[1]] = price_feed_addresses[1]

@external
def deposit_collateral(token_collateral_address: address, amount_collateral: uint256):
    self._deposit_collateral(token_collateral_address, amount_collateral)

@internal
@nonreentrant('lock')
def _deposit_collateral(token_collateral_address: address, amount_collateral: uint256):
    assert amount_collateral > 0, "DSCEngine_NeedsMoreThanZero"
    assert self.token_address_to_price_feed[token_collateral_address] != empty(address), "DSCEngine__TokenNotAllowed"

    self.user_to_token_address_to_amount_deposited[msg.sender][token_collateral_address] += amount_collateral
    log CollateralDeposited(msg.sender, amount_collateral)
    success: bool = ERC20(token_collateral_address).transferFrom(msg.sender, self, amount_collateral)
    assert success, "DSCEngine_TransferFailed"


@external
def deposit_collateral_and_mint_dsc(token_collateral_address: address, amount_collateral: uint256, amount_dsc_to_mint: uint256):
    self._deposit_collateral(token_collateral_address, amount_collateral)
    self._mint_dsc(amount_dsc_to_mint)

@external 
def redeem_collateral_for_dsc(token_collateral_address: address, amount_collateral: uint256, amount_dsc_to_burn: uint256):
    self._burn_dsc(amount_dsc_to_burn, msg.sender, msg.sender)
    self._redeem_collateral(token_collateral_address, amount_collateral, msg.sender, msg.sender)
    self._revert_if_health_factor_is_broken(msg.sender)

@external
def mint_dsc(amount_dsc_to_mint: uint256):
    self._mint_dsc(amount_dsc_to_mint)

@internal
@nonreentrant('lock')
def _mint_dsc(amount_dsc_to_mint: uint256):
    assert amount_dsc_to_mint > 0, "DSCEngine_NeedsMoreThanZero"
    self.user_to_dsc_minted[msg.sender] += amount_dsc_to_mint
    self._revert_if_health_factor_is_broken(msg.sender)
    minted: bool = DSC.mint(msg.sender, amount_dsc_to_mint)
    assert minted, "DSCEngine_MintFailed"

@external
@nonreentrant("liquidate")
def liquidate(collateral: address, user: address, debt_to_cover: uint256):
    assert debt_to_cover > 0, "DSCEngine_NeedsMoreThanZero"
    
    starting_user_health_factor: uint256 = self._health_factor(user)
    assert starting_user_health_factor < MIN_HEALTH_FACTOR, "DSCEngine_HealthFactorOk"

    token_amount_from_debt_covered: uint256 = self._get_token_amount_from_usd(collateral, debt_to_cover)
    bonus_collateral: uint256 = (token_amount_from_debt_covered * LIQUIDATION_BONUS) / 100
    self._redeem_collateral(collateral, token_amount_from_debt_covered + bonus_collateral, user, msg.sender)
    self._burn_dsc(debt_to_cover, user, msg.sender)

    ending_user_health_factor: uint256 = self._health_factor(user)
    assert ending_user_health_factor > starting_user_health_factor, "DSCEngine_HealthFactorNotImproved"
    self._revert_if_health_factor_is_broken(msg.sender)


@external
def redeem_collateral(token_collateral_address: address, amount_collateral: uint256):
    self._redeem_collateral(token_collateral_address, amount_collateral, msg.sender, msg.sender)
    self._revert_if_health_factor_is_broken(msg.sender)

@internal
@nonreentrant('lock')
def _redeem_collateral(token_collateral_address: address, amount_collateral: uint256, _from: address, _to: address):
    self.user_to_token_address_to_amount_deposited[_from][token_collateral_address] -= amount_collateral
    log CollateralRedeemed(_from, amount_collateral, _from, _to)
    success: bool = ERC20(token_collateral_address).transfer(_to, amount_collateral)
    assert success, "DSCEngine_TransferFailed"

@external
def burn_dsc(amount_dsc_to_burn: uint256):
    self._burn_dsc(amount_dsc_to_burn, msg.sender, msg.sender)
    self._revert_if_health_factor_is_broken(msg.sender)

@internal
@nonreentrant('lock')
def _burn_dsc(amount_dsc_to_burn: uint256, on_behalf_of: address, dsc_from: address):
    self.user_to_dsc_minted[on_behalf_of] -= amount_dsc_to_burn
    success: bool = DSC.burnFrom(dsc_from, amount_dsc_to_burn)
    assert success, "DSCEngine_BurnFailed"

@view
@internal
def _get_account_information(user: address) -> (uint256, uint256):
    total_dsc_minted: uint256 = self.user_to_dsc_minted[user]
    collateral_value_in_usd: uint256 = self._get_account_collateral_value(user) 
    return total_dsc_minted, collateral_value_in_usd

@external
@view
def health_factor(user: address) -> uint256:
    return self._health_factor(user)

@view
@internal
def _health_factor(user: address) -> uint256:
    total_dsc_minted: uint256 = 0
    collateral_value_in_usd: uint256 = 0
    total_dsc_minted, collateral_value_in_usd = self._get_account_information(user)
    return self._calculate_health_factor(total_dsc_minted, collateral_value_in_usd)

@view
@internal
def _get_usd_value(token: address, amount: uint256) -> uint256:
    price_feed: AggregatorV3Interface = AggregatorV3Interface(self.token_address_to_price_feed[token])
    round_id: uint80 = 0
    price: int256 = 0
    started_at: uint256 = 0
    updated_at: uint256 = 0
    answered_in_round: uint80 = 0
    (round_id, price, started_at, updated_at, answered_in_round) = self._stale_check_latest_round_data(price_feed.address)
    return ((convert(price, uint256) * ADDITIONAL_FEED_PRECISION) * amount) / PRECISION

@pure
@internal
def _calculate_health_factor(total_dsc_minted: uint256, collateral_value_in_usd: uint256) -> uint256:
    if total_dsc_minted == 0:
        return max_value(uint256)
    collateral_adjusted_for_threshold: uint256 = (collateral_value_in_usd * LIQUIDATION_THRESHOLD) / 100
    return (collateral_adjusted_for_threshold * (10 ** 18)) / total_dsc_minted

@internal
def _revert_if_health_factor_is_broken(user: address):
    user_health_factor: uint256 = self._health_factor(user)
    assert user_health_factor >= MIN_HEALTH_FACTOR, "DSCEngine_BreaksHealthFactor"

@external
@pure
def calculate_health_factor(total_dsc_minted: uint256, collateral_value_in_usd: uint256) -> uint256:
    return self._calculate_health_factor(total_dsc_minted, collateral_value_in_usd)

@external
@view
def get_account_information(user: address) -> (uint256, uint256):
    return self._get_account_information(user)

@external
@view
def get_usd_value(token: address, amount: uint256) -> uint256:
    return self._get_usd_value(token, amount) 

@external
@view
def get_collateral_balance_of_user(user: address, token: address) -> uint256:
    return self.user_to_token_address_to_amount_deposited[user][token]

@external
@view
def get_account_collateral_value(user: address) -> uint256:
    return self._get_account_collateral_value(user)

@internal
@view
def _get_account_collateral_value(user: address) -> uint256:
    total_collateral_value_in_usd: uint256 = 0
    for token in COLLATERAL_TOKENS:
        amount: uint256 = self.user_to_token_address_to_amount_deposited[user][token]
        total_collateral_value_in_usd += self._get_usd_value(token, amount)
    return total_collateral_value_in_usd


@external
@view
def get_token_amount_from_usd(token: address, usd_amount_in_wei: uint256) -> uint256:
    return self._get_token_amount_from_usd(token, usd_amount_in_wei)

@internal
@view
def _get_token_amount_from_usd(token: address, usd_amount_in_wei: uint256) -> uint256:
    price_feed: AggregatorV3Interface = AggregatorV3Interface(self.token_address_to_price_feed[token])
    round_id: uint80 = 0
    price: int256 = 0
    started_at: uint256 = 0
    updated_at: uint256 = 0
    answered_in_round: uint80 = 0
    (round_id, price, started_at, updated_at, answered_in_round) = self._stale_check_latest_round_data(price_feed.address)
    return ((usd_amount_in_wei * PRECISION) / (convert(price, uint256) * ADDITIONAL_FEED_PRECISION))

# Chainlink Lib

# SPDX-License-Identifier: MIT
# @version 0.3.7
# """
# @author Patrick Collins
# @notice This library is used to check the Chainlink Oracle for stale data.
#     If a price is stale, functions will revert, and render the DSCEngine unusable - this is by design.
#     We want the DSCEngine to freeze if prices become stale.

#     So if the Chainlink network explodes and you have a lot of money locked in the protocol... too bad.
# """

# Constants
TIMEOUT: constant(uint256) = 3 * 3600

@external
@view
def stale_check_latest_round_data(chainlink_feed: address) -> (uint80, int256, uint256, uint256, uint80):
    return self._stale_check_latest_round_data(chainlink_feed)

@internal
@view
def _stale_check_latest_round_data(price_price_address: address) -> (uint80, int256, uint256, uint256, uint80):
    price_price: AggregatorV3Interface = AggregatorV3Interface(price_price_address)

    round_id: uint80 = 0
    price: int256 = 0
    started_at: uint256 = 0
    updated_at: uint256 = 0
    answered_in_round: uint80 = 0
    (round_id, price, started_at, updated_at, answered_in_round) = price_price.latestRoundData()

    assert updated_at != 0, "DSCEngine_StalePrice"
    assert answered_in_round >= round_id, "DSCEngine_StalePrice"

    seconds_since: uint256 = block.timestamp - updated_at
    assert seconds_since <= TIMEOUT, "DSCEngine_StalePrice"

    return (round_id, price, started_at, updated_at, answered_in_round)
