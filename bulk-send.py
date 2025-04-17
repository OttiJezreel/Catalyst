import toml
import os
from web3 import Web3
from web3.exceptions import InvalidAddress

# Load configuration from settings.toml
with open("settings.toml", "r") as file:
    config = toml.load(file)

PRIVATE_KEY = config["settings"]["private_key"]
MONAD_RPC_URL = "https://testnet-rpc.monad.xyz"
CHAIN_ID = 10143

# Connect to Monad testnet
w3 = Web3(Web3.HTTPProvider(MONAD_RPC_URL))
if not w3.is_connected():
    raise Exception("Failed to connect to Monad testnet")

# Wallet setup
account = w3.eth.account.from_key(PRIVATE_KEY)
wallet_address = account.address

# TokenDistributor contract details
CONTRACT_ADDRESS = "0xC36eb65362eF39E26FC4e483Ed032Aa19D9f85d1"
CONTRACT_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "tokenAddress", "type": "address"},
            {"name": "totalAmount", "type": "uint256"},
            {"name": "recipients", "type": "address[]"}
        ],
        "name": "distributeTokens",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "tokenAddress", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "withdrawTokens",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ERC20 ABI (minimal for balanceOf, approve)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "success-maximum", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Token list
TOKENS = {
    "MON": {"address": "0x0000000000000000000000000000000000000000", "decimals": 18, "name": "Native MON"},
    "USDT": {"address": "0x88b8E2161DEDC77EF4ab7585569D2415a1C1055D", "decimals": 6, "name": "Tether USD"},
    "USDC": {"address": "0xf817257fed379853cDe0fa4F97AB987181B1E5Ea", "decimals": 6, "name": "USD Coin"},
    "WMON": {"address": "0x760AfE86e5de5fa0Ee542fc7B7B713e1c5425701", "decimals": 18, "name": "Wrapped MON"}
}

contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

def is_valid_address(address):
    try:
        w3.to_checksum_address(address)
        return True
    except (InvalidAddress, ValueError):
        return False

def get_token_balance(token_info, address):
    if token_info["address"] == "0x0000000000000000000000000000000000000000":
        balance = w3.eth.get_balance(address)
        balance_readable = balance / 10**token_info["decimals"]
        return balance, balance_readable
    else:
        if not is_valid_address(token_info["address"]):
            raise ValueError(f"Invalid token address: {token_info['address']}")
        token_contract = w3.eth.contract(address=token_info["address"], abi=ERC20_ABI)
        balance = token_contract.functions.balanceOf(address).call()
        balance_readable = balance / 10**token_info["decimals"]
        return balance, balance_readable

def approve_token(token_address, amount):
    if not is_valid_address(token_address):
        raise ValueError(f"Invalid token address: {token_address}")
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    tx = token_contract.functions.approve(CONTRACT_ADDRESS, amount).build_transaction({
        "from": wallet_address,
        "nonce": w3.eth.get_transaction_count(wallet_address),
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID
    })
    signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.status == 1

def distribute_tokens(token_info, total_amount, recipients):
    amount_wei = int(total_amount * 10**token_info["decimals"])
    
    tx_params = {
        "from": wallet_address,
        "nonce": w3.eth.get_transaction_count(wallet_address),
        "gas": 2000000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID
    }
    
    if token_info["address"] == "0x0000000000000000000000000000000000000000":
        tx_params["value"] = amount_wei
    else:
        if not approve_token(token_info["address"], amount_wei):
            raise Exception("Token approval failed")
        tx_params["value"] = 0
    
    tx = contract.functions.distributeTokens(
        w3.to_checksum_address(token_info["address"]),
        amount_wei,
        recipients
    ).build_transaction(tx_params)
    
    signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.status == 1, tx_hash.hex()

def withdraw_tokens(token_info, amount):
    """Call withdrawTokens on the TokenDistributor contract."""
    amount_wei = int(amount * 10**token_info["decimals"])
    
    balance_wei, balance_readable = get_token_balance(token_info, CONTRACT_ADDRESS)
    if balance_wei < amount_wei:
        raise Exception(f"Insufficient balance in contract: {balance_readable} {token_info['name']}")
    
    tx = contract.functions.withdrawTokens(
        w3.to_checksum_address(token_info["address"]),
        amount_wei
    ).build_transaction({
        "from": wallet_address,
        "nonce": w3.eth.get_transaction_count(wallet_address),
        "gas": 100000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID
    })
    
    signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.status == 1, tx_hash.hex()

def select_token():
    """Prompt user to select a token by number, including custom token option."""
    print("\nAvailable tokens:")
    token_list = list(TOKENS.keys())
    for i, token in enumerate(token_list, 1):
        print(f"{i}. {TOKENS[token]['name']} ({token})")
    print(f"{len(token_list) + 1}. Custom Token")
    
    try:
        choice = int(input(f"Select token (1-{len(token_list) + 1}): "))
        if 1 <= choice <= len(token_list):
            return token_list[choice - 1], TOKENS[token_list[choice - 1]]
        elif choice == len(token_list) + 1:
            # Custom token input
            custom_address = input("Enter custom token contract address: ").strip()
            if not is_valid_address(custom_address):
                print("Invalid contract address!")
                return None, None
            try:
                custom_decimals = int(input("Enter token decimals (e.g., 6 for USDT, 18 for WMON): "))
                if custom_decimals < 0:
                    raise ValueError("Decimals must be non-negative")
            except ValueError:
                print("Invalid decimals! Please enter a non-negative integer.")
                return None, None
            custom_name = input("Enter token name (optional, press Enter for 'Custom Token'): ").strip()
            if not custom_name:
                custom_name = "Custom Token"
            custom_token = {
                "address": custom_address,
                "decimals": custom_decimals,
                "name": custom_name
            }
            return "CUSTOM", custom_token
        else:
            print(f"Invalid selection! Choose a number between 1 and {len(token_list) + 1}.")
            return None, None
    except ValueError:
        print("Invalid input! Please enter a number.")
        return None, None

def main():
    while True:
        print("\nToken Distributor Bot")
        print("1. Distribute Tokens")
        print("2. Withdraw Tokens")
        print("3. Exit")
        choice = input("Select an option (1-3): ")
        
        if choice == "3":
            print("Exiting...")
            break
        
        if choice not in ["1", "2"]:
            print("Invalid option!")
            continue
        
        # Select token
        token_symbol, token_info = select_token()
        if not token_symbol or not token_info:
            continue
        
        try:
            wallet_balance_wei, wallet_balance_readable = get_token_balance(token_info, wallet_address)
            contract_balance_wei, contract_balance_readable = get_token_balance(token_info, CONTRACT_ADDRESS)
            print(f"Your {token_info['name']} balance: {wallet_balance_readable} {token_symbol}")
            print(f"Contract {token_info['name']} balance: {contract_balance_readable} {token_symbol}")
        except Exception as e:
            print(f"Error fetching balances: {e}")
            print("Please verify the token address and ensure it’s a valid ERC20 contract.")
            continue
        
        if choice == "1":
            try:
                total_amount = float(input(f"Enter total amount to distribute (in {token_info['name']}): "))
                if total_amount <= 0:
                    raise ValueError("Amount must be positive")
            except ValueError as e:
                print(f"Invalid amount: {e}")
                continue
            
            recipients_input = input("Enter recipient addresses (space-separated, e.g., 0x89283 0x628277): ")
            recipients = recipients_input.strip().split()
            if not recipients:
                print("No recipients provided!")
                continue
            
            try:
                recipients = [w3.to_checksum_address(addr) for addr in recipients]
            except ValueError:
                print("Invalid address format!")
                continue
            
            print(f"\nDistribution Summary:")
            print(f"Token: {token_info['name']}")
            print(f"Total Amount: {total_amount} {token_symbol}")
            print(f"Recipients ({len(recipients)}): {', '.join(recipients)}")
            print(f"Amount per recipient: {total_amount / len(recipients)} {token_symbol}")
            confirm = input("Proceed with distribution? (y/n): ").lower()
            
            if confirm != 'y':
                print("Distribution cancelled.")
                continue
            
            try:
                success, tx_hash = distribute_tokens(token_info, total_amount, recipients)
                if success:
                    print(f"Distribution successful! Transaction hash: {tx_hash}")
                else:
                    print("Distribution failed. Check transaction receipt for details.")
            except Exception as e:
                print(f"Error during distribution: {e}")
        
        elif choice == "2":
            try:
                amount = float(input(f"Enter amount to withdraw from contract (in {token_info['name']}): "))
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except ValueError as e:
                print(f"Invalid amount: {e}")
                continue
            
            print(f"\nWithdrawal Summary:")
            print(f"Token: {token_info['name']}")
            print(f"Amount: {amount} {token_symbol}")
            print(f"Contract balance: {contract_balance_readable} {token_symbol}")
            confirm = input("Proceed with withdrawal? (y/n): ").lower()
            
            if confirm != 'y':
                print("Withdrawal cancelled.")
                continue
            
            try:
                success, tx_hash = withdraw_tokens(token_info, amount)
                if success:
                    print(f"Withdrawal successful! Transaction hash: {tx_hash}")
                else:
                    print("Withdrawal failed. Check transaction receipt for details.")
            except Exception as e:
                print(f"Error during withdrawal: {e}")

if __name__ == "__main__":
    main()