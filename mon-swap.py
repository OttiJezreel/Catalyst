from web3 import Web3
import time
import json
import os
import toml

with open("settings.toml", "r") as file:
    config = toml.load(file)

PRIVATE_KEY = config["settings"]["private_key"]

MONAD_RPC_URL = "https://testnet-rpc.monad.xyz"
CHAIN_ID = 10143

ROUTER_OPTIONS = {
    1: ("Octoswap", "0xb6091233aAcACbA45225a2B2121BBaC807aF4255"),
    2: ("Mondafund", "0xc80585f78A6e44fb46e1445006f820448840386e"),
    3: ("Bean Exchange", "0xCa810D095e90Daae6e867c19DF6D9A8C56db2c89"),
    4: ("Monad Madness", "0x64Aff7245EbdAAECAf266852139c67E4D8DBa4de")
}

print("Select a router:")
for num, (name, _) in ROUTER_OPTIONS.items():
    print(f"{num}. {name}")
try:
    router_choice = int(input("Enter number: "))
    if router_choice not in ROUTER_OPTIONS:
        print("Invalid router choice.")
        exit()
    ROUTER_ADDRESS = ROUTER_OPTIONS[router_choice][1]
except ValueError:
    print("Please enter a valid number.")
    exit()

WMON_ADDRESS = "0x760AfE86e5de5fa0Ee542fc7B7B713e1c5425701"
USDT_ADDRESS = "0x88b8E2161DEDC77EF4ab7585569D2415a1C1055D"
USDC_ADDRESS = "0xf817257fed379853cDe0fa4F97AB987181B1E5Ea"

TOKENS = {
    "MON": "0x0000000000000000000000000000000000000000",  # Gas token (ETH)
    "wMON": WMON_ADDRESS,
    "USDT": USDT_ADDRESS,
    "USDC": USDC_ADDRESS
}

w3 = Web3(Web3.HTTPProvider(MONAD_RPC_URL))
if not w3.is_connected():
    print("Failed to connect to Monad Testnet")
    exit()

account = w3.eth.account.from_key(PRIVATE_KEY)

ROUTER_ABI = json.loads('''
[
    {
        "constant": false,
        "inputs": [
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "payable": true,
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "payable": false,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "amountOutMin", "type": "uint256"},
            {"name": "path", "type": "address[]"},
            {"name": "to", "type": "address"},
            {"name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [{"name": "amounts", "type": "uint256[]"}],
        "payable": false,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
''')

WMON_ABI = json.loads('''
[
    {
        "constant": false,
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "payable": true,
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [{"name": "wad", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "payable": false,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]
''')

ERC20_ABI = json.loads('''
[
    {
        "constant": false,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": false,
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    }
]
''')

router_contract = w3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
wmon_deposit_contract = w3.eth.contract(address=WMON_ADDRESS, abi=WMON_ABI)
token_contracts = {
    "wMON": w3.eth.contract(address=WMON_ADDRESS, abi=ERC20_ABI),
    "USDT": w3.eth.contract(address=USDT_ADDRESS, abi=ERC20_ABI),
    "USDC": w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
}

token_decimals = {}
token_decimals["MON"] = 18 
for token, contract in token_contracts.items():
    token_decimals[token] = contract.functions.decimals().call()

GAS_PRICE = w3.to_wei(52, "gwei")
GAS_LIMIT_APPROVE = 50000
GAS_LIMIT_SWAP = 160000
GAS_LIMIT_DEPOSIT = 30000
GAS_LIMIT_WITHDRAW = 40000 

def get_balances():
    balances = {}
    balances["MON"] = w3.eth.get_balance(account.address) / (10 ** token_decimals["MON"])
    for token, contract in token_contracts.items():
        balance_wei = contract.functions.balanceOf(account.address).call()
        balances[token] = balance_wei / (10 ** token_decimals[token])
    return balances

def get_deadline():
    return int(time.time()) + 600

token_list = ["MON", "wMON", "USDT", "USDC"]

nonce = w3.eth.get_transaction_count(account.address)
while True:
    balances = get_balances()
    print("\nCurrent balances:")
    for token in token_list:
        print(f"{token}: {balances[token]:.4f}")

    while True:
        print("\nSelect token to swap from:")
        for i, token in enumerate(token_list, 1):
            print(f"{i}. {token}")
        try:
            choice = int(input("Enter number: "))
            if 1 <= choice <= len(token_list):
                from_token = token_list[choice - 1]
                break
            else:
                print("Number out of range.")
        except ValueError:
            print("Please enter a valid number.")

    while True:
        print("\nSelect token to swap to:")
        for i, token in enumerate(token_list, 1):
            print(f"{i}. {token}")
        try:
            choice = int(input("Enter number: "))
            if 1 <= choice <= len(token_list):
                to_token = token_list[choice - 1]
                break
            else:
                print("Number out of range.")
        except ValueError:
            print("Please enter a valid number.")

    if from_token == to_token:
        print("Cannot swap to the same token.")
        continue

    try:
        amount = float(input("Enter amount to swap: "))
        if amount <= 0:
            print("Amount must be positive.")
            continue
        if from_token == "MON":
            if amount > balances["MON"]:
                print("Insufficient MON balance.")
                continue
        else:
            if amount > balances[from_token]:
                print(f"Insufficient {from_token} balance.")
                continue
    except ValueError:
        print("Amount must be a number.")
        continue

    if from_token == "MON" and to_token == "wMON":
        function = wmon_deposit_contract.functions.deposit()
        value = int(amount * (10 ** token_decimals["MON"]))
        gas = GAS_LIMIT_DEPOSIT
    elif from_token == "wMON" and to_token == "MON":
        function = wmon_deposit_contract.functions.withdraw(
            int(amount * (10 ** token_decimals["wMON"]))
        )
        value = 0
        gas = GAS_LIMIT_WITHDRAW
    else:
        if from_token == "MON":
            path = [WMON_ADDRESS, TOKENS[to_token]]
            function = router_contract.functions.swapExactETHForTokens(
                0,
                path,
                account.address,
                get_deadline()
            )
            value = int(amount * (10 ** token_decimals["MON"]))
        elif to_token == "MON":
            path = [TOKENS[from_token], WMON_ADDRESS]
            function = router_contract.functions.swapExactTokensForETH(
                int(amount * (10 ** token_decimals[from_token])),
                0,
                path,
                account.address,
                get_deadline()
            )
            value = 0
        else:
            path = [TOKENS[from_token], TOKENS[to_token]]
            function = router_contract.functions.swapExactTokensForTokens(
                int(amount * (10 ** token_decimals[from_token])),
                0,
                path,
                account.address,
                get_deadline()
            )
            value = 0
        gas = GAS_LIMIT_SWAP

        if from_token != "MON" and to_token != "MON": 
            approve_function = token_contracts[from_token].functions.approve(
                ROUTER_ADDRESS, 2**256 - 1
            )
            approve_tx = approve_function.build_transaction({
                "from": account.address,
                "gas": GAS_LIMIT_APPROVE,
                "gasPrice": GAS_PRICE,
                "nonce": nonce,
                "chainId": CHAIN_ID
            })
            signed_approve_tx = account.sign_transaction(approve_tx)
            tx_hash = w3.eth.send_raw_transaction(signed_approve_tx.rawTransaction)
            print(f"Approval transaction sent: {tx_hash.hex()}")
            w3.eth.wait_for_transaction_receipt(tx_hash)
            nonce += 1

    tx = function.build_transaction({
        "from": account.address,
        "value": value,
        "gas": gas,
        "gasPrice": GAS_PRICE,
        "nonce": nonce,
        "chainId": CHAIN_ID
    })
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print(f"Transaction sent: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status == 1:
        print("Transaction successful")
    else:
        print("Transaction failed")
    nonce += 1

    choice = input("Enter 'q' to quit or any other key to continue: ").lower()
    if choice == "q":
        break
