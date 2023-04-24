from brownie import reverts


def test_must_mint_more_than_zero(dsc, account):
    with reverts():
        dsc.mint(account, 0, {"from": account})


def test_cant_mint_to_zero_address(dsc, account, zero_address):
    with reverts():
        dsc.mint(zero_address, 1, {"from": account})


# Can you add more tests?
