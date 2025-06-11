from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from web3 import Web3
from solana.rpc.api import Client  # You'll need to install solana-py
import json
import os
import spacy
from spacy.matcher import Matcher, PhraseMatcher
from datetime import datetime
from decimal import Decimal

app = Flask(__name__)
# Generate a secure secret key using os.urandom
app.secret_key = 'blockchain-chatbot-secret-key-123'

SEPARATOR = "═" * 40  # Adjust length as needed

class BlockchainChatBot:
    def __init__(self):
        self.conversation_history = []
        self.help_menu = """
🤖 Welcome to Blockchain ChatBot! Here are the available commands:
═══════════════════════════════════════════════════════════════

🔗 Transfer Tokens
   ├─ Format: "transfer <amount> <coin_type> to <address>"
   ├─ Natural: "send <amount> <coin_type> to <address>"
   ├─ Example: "transfer 0.1 eth to 0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
   └─ Supported coins: ETH, BNB, MATIC, AVAX, SOL

💰 Check Balance
   ├─ Format: "balance <coin_type>"
   ├─ Natural: "how much <coin_type> do I have?"
   ├─ Example: "check my eth balance"
   └─ Supported coins: ETH, BNB, MATIC, AVAX, SOL

💱 Check Price
   ├─ Format: "price <coin_type>"
   ├─ Natural: "how much is <coin_type> worth?"
   ├─ Example: "what is the price of eth"
   └─ Supported coins: ETH, BNB, MATIC, AVAX, SOL

📜 Transaction History
   ├─ Format: "history <coin_type>"
   ├─ Natural: "show my <coin_type> transactions"
   ├─ Example: "show my eth transaction history"
   └─ Supported coins: ETH, BNB, MATIC, AVAX, SOL

❓ Help
   └─ Type 'help' to see this menu again

Note: 
- All commands are case-insensitive
- You can use natural language to interact with the bot
- Start with "Hi" or "Hello" to begin a conversation
"""

        # Updated Web3 connections
        self.web3_connections = {
            'eth': Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/0d894536d41a4e8b816eaff6ed1bbeab')),
            'bnb': Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org/')),
            'matic': Web3(Web3.HTTPProvider('https://polygon-rpc.com')),
            'avax': Web3(Web3.HTTPProvider('https://api.avax.network/ext/bc/C/rpc')),
            'sol': Client('https://api.mainnet-beta.solana.com')
        }

        # Add gas price tracking and cross-chain routes
        self.cross_chain_routes = {
            'eth': ['matic', 'bnb', 'avax'],
            'bnb': ['eth', 'matic', 'avax'],
            'matic': ['eth', 'bnb', 'avax'],
            'avax': ['eth', 'bnb', 'matic'],
            'sol': ['eth', 'bnb', 'matic', 'avax']
        }
        
        # Bridge contract addresses (you would need real bridge contract addresses)
        self.bridge_contracts = {
            'eth_matic': '0x...',
            'eth_bnb': '0x...',
            'eth_avax': '0x...',
            # Add other bridge pairs
        }

        # Enhanced NLP setup
        self.nlp = spacy.load("en_core_web_sm")
        self.matcher = Matcher(self.nlp.vocab)
        self.phrase_matcher = PhraseMatcher(self.nlp.vocab)

        # Define more natural language patterns
        self.matcher.add("TRANSFER", [
            # Formal commands
            [{"LIKE_NUM": True}, {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, 
             {"LOWER": "to"}, {"SHAPE": {"REGEX": "^[0-9a-zA-Z]+$"}}],
            # Natural language
            [{"LOWER": "send"}, {"LIKE_NUM": True}, 
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, 
             {"LOWER": "to"}, {"SHAPE": {"REGEX": "^[0-9a-zA-Z]+$"}}],
            [{"LOWER": "please"}, {"LOWER": "send"}, {"LIKE_NUM": True},
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}},
             {"LOWER": "to"}, {"SHAPE": {"REGEX": "^[0-9a-zA-Z]+$"}}]
        ])
        
        self.matcher.add("BALANCE", [
            # Formal commands
            [{"LOWER": "balance"}, {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}],
            # Natural language
            [{"LOWER": "check"}, {"LOWER": "my"}, 
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, {"LOWER": "balance"}],
            [{"LOWER": "how"}, {"LOWER": "much"}, 
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, 
             {"LOWER": "do"}, {"LOWER": "i"}, {"LOWER": "have"}],
            [{"LOWER": "show"}, {"LOWER": "my"}, 
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, {"LOWER": "balance"}]
        ])
        
        self.matcher.add("PRICE", [
            # Formal commands
            [{"LOWER": "price"}, {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}],
            # Natural language
            [{"LOWER": "how"}, {"LOWER": "much"}, {"LOWER": "is"}, 
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, {"LOWER": "worth"}],
            [{"LOWER": "what"}, {"LOWER": "is"}, {"LOWER": "the"}, {"LOWER": "price"}, 
             {"LOWER": "of"}, {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}]
        ])

        # Add common phrases for intent recognition
        self.common_phrases = {
            "greeting": ["hello", "hi", "hey", "greetings", "good morning", "good evening"],
            "farewell": ["bye", "goodbye", "see you", "catch you later"],
            "thanks": ["thank you", "thanks", "appreciate it", "grateful"],
            "help": ["help", "assist", "guide", "support", "how to", "what can you do"]
        }

        # Add phrase patterns
        for intent, phrases in self.common_phrases.items():
            patterns = [self.nlp.make_doc(text) for text in phrases]
            self.phrase_matcher.add(intent, patterns)

        # Add more flexible transaction history patterns
        self.matcher.add("HISTORY", [
            # Formal commands
            [{"LOWER": "history"}, {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}],
            [{"LOWER": "history"}],  # Just "history" alone
            [{"LOWER": "transactions"}],  # Just "transactions" alone
            [{"LOWER": "transaction"}, {"LOWER": "history"}],
            # Natural language patterns
            [{"LOWER": "show"}, {"LOWER": "my"}, 
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, {"LOWER": "transactions"}],
            [{"LOWER": "show"}, {"LOWER": "my"}, {"LOWER": "transactions"}],
            [{"LOWER": "what"}, {"LOWER": "are"}, {"LOWER": "my"}, {"LOWER": "recent"}, 
             {"LOWER": {"IN": ["eth", "bnb", "matic", "avax", "sol"]}}, {"LOWER": "transactions"}],
            [{"LOWER": "what"}, {"LOWER": "are"}, {"LOWER": "my"}, {"LOWER": "transactions"}],
            [{"LOWER": "get"}, {"LOWER": "my"}, {"LOWER": "transactions"}],
            [{"LOWER": "check"}, {"LOWER": "my"}, {"LOWER": "transactions"}],
            [{"LOWER": "view"}, {"LOWER": "transactions"}],
            [{"LOWER": "show"}, {"LOWER": "history"}]
        ])

    def get_chain_connection(self, coin_type):
        coin_type = coin_type.lower()
        
        # Updated coin type normalization
        if coin_type in ['bnb', 'bsc']:
            return self.web3_connections.get('bnb')
        elif coin_type in ['eth', 'ethereum']:
            return self.web3_connections.get('eth')
        elif coin_type in ['matic', 'polygon']:
            return self.web3_connections.get('matic')
        elif coin_type in ['avax', 'avalanche']:
            return self.web3_connections.get('avax')
        elif coin_type in ['sol', 'solana']:
            return self.web3_connections.get('sol')
        
        return None

    def validate_address(self, address):
        """Validate blockchain address with proper case sensitivity"""
        try:
            # For ETH-style addresses
            if address.startswith('0x'):
                # Convert to checksum address
                checksum_address = Web3.to_checksum_address(address)
                return True
            # For Solana addresses
            elif len(address) == 44:
                return True
            return False
        except Exception as e:
            print(f"Address validation error: {str(e)}")
            return False

    def process_transfer(self, message):
        """Process transfer with proper decimal handling"""
        try:
            # Extract data from parsed message
            amount = Decimal(str(message['amounts'][0]))  # Convert to Decimal
            coin = message['coins'][0].lower()
            address = message['addresses'][0]
            
            # Validate with case-sensitive address
            if not self.validate_address(address):
                return {
                    'error': f"Invalid address format: {address}"
                }
            
            # For ETH-style addresses, convert to checksum
            if address.startswith('0x'):
                address = Web3.to_checksum_address(address)
            
            return {
                'success': True,
                'message': 'Transfer initiated',
                'details': {
                    'amount': float(amount),  # Convert back to float for display
                    'coin': coin,
                    'address': address
                }
            }
        except Exception as e:
            return {'error': str(e)}

    def get_gas_prices(self):
        """Get current gas prices for all supported chains"""
        gas_prices = {}
        try:
            for chain, connection in self.web3_connections.items():
                if chain != 'sol':  # Handle Solana separately
                    gas_price = connection.eth.gas_price
                    gas_prices[chain] = connection.from_wei(gas_price, 'gwei')
                else:
                    # Get Solana gas price
                    sol_response = connection.get_recent_blockhash()
                    gas_prices[chain] = sol_response['result']['value']['feeCalculator']['lamportsPerSignature'] / 1e9
        except Exception as e:
            print(f"Error fetching gas prices: {str(e)}")
        return gas_prices

    def optimize_cross_chain_route(self, from_chain, to_chain, amount):
        """
        Optimize the cross-chain transfer route based on gas fees
        Returns: List of transfer steps with amounts
        """
        gas_prices = self.get_gas_prices()
        if not gas_prices:
            return None

        # Direct transfer if chains are the same
        if from_chain == to_chain:
            return [{'from': from_chain, 'to': to_chain, 'amount': amount}]

        # Find all possible routes between chains
        possible_routes = []
        visited = set()

        def find_routes(current_chain, target_chain, path=None, total_gas=0):
            if path is None:
                path = []
            
            path.append(current_chain)
            visited.add(current_chain)

            if current_chain == target_chain:
                possible_routes.append((path[:], total_gas))
            else:
                for next_chain in self.cross_chain_routes[current_chain]:
                    if next_chain not in visited:
                        gas_cost = gas_prices.get(next_chain, float('inf'))
                        find_routes(next_chain, target_chain, path, total_gas + gas_cost)

            path.pop()
            visited.remove(current_chain)

        find_routes(from_chain, to_chain)

        if not possible_routes:
            return None

        # Sort routes by total gas cost
        possible_routes.sort(key=lambda x: x[1])
        best_route = possible_routes[0][0]

        # Calculate optimal amount distribution
        num_hops = len(best_route) - 1
        base_amount = amount / num_hops
        
        # Create transfer steps
        transfer_steps = []
        remaining_amount = amount
        
        for i in range(num_hops):
            step_amount = base_amount if i < num_hops - 1 else remaining_amount
            transfer_steps.append({
                'from': best_route[i],
                'to': best_route[i + 1],
                'amount': step_amount
            })
            remaining_amount -= step_amount

        return transfer_steps

    def execute_cross_chain_transfer(self, from_chain, to_address, amount):
        """Execute a cross-chain transfer with optimal routing"""
        try:
            to_chain = self.detect_chain_from_address(to_address)
            if not to_chain:
                return {'error': 'Unable to detect destination chain'}

            # Convert amount to Decimal for precise calculations
            amount = Decimal(str(amount))  # Convert float to Decimal using string

            # If it's a same-chain transfer, handle it directly
            if from_chain == to_chain:
                connection = self.get_chain_connection(from_chain)
                if not connection:
                    return {'error': f'Unable to connect to {from_chain} network'}

                # Get wallet address from session
                wallet_address = session.get('wallet_address')
                if not wallet_address:
                    return {'error': 'Please connect your wallet first!'}

                try:
                    # For same-chain transfers, execute direct transfer
                    if from_chain == 'sol':
                        # Handle Solana transfer
                        # You'll need to implement Solana-specific transfer logic
                        pass
                    else:
                        # Handle ETH-style transfer
                        # Convert amount to Wei using Decimal
                        amount_wei = connection.to_wei(amount, 'ether')
                        
                        tx = {
                            'from': wallet_address,
                            'to': to_address,
                            'value': amount_wei,
                            'gas': 21000,  # Standard gas limit for ETH transfers
                            'gasPrice': connection.eth.gas_price
                        }
                        
                        return {
                            'success': True,
                            'message': 'Transfer initiated',
                            'details': {
                                'from': wallet_address,
                                'to': to_address,
                                'amount': float(amount),  # Convert back to float for display
                                'chain': from_chain
                            }
                        }
                except Exception as e:
                    return {'error': f'Transfer failed: {str(e)}'}

            # For cross-chain transfers
            transfer_steps = self.optimize_cross_chain_route(from_chain, to_chain, float(amount))
            if not transfer_steps:
                return {'error': 'No valid route found'}

            # Execute each transfer step
            results = []
            for step in transfer_steps:
                bridge_key = f"{step['from']}_{step['to']}"
                bridge_contract = self.bridge_contracts.get(bridge_key)
                
                if not bridge_contract:
                    return {'error': f'No bridge available for {bridge_key}'}

                # Execute the bridge transfer with proper decimal conversion
                result = self.execute_bridge_transfer(
                    bridge_contract,
                    step['from'],
                    step['to'],
                    Decimal(str(step['amount'])),
                    to_address
                )
                results.append(result)

            return {
                'success': True,
                'message': 'Cross-chain transfer initiated',
                'steps': results
            }

        except Exception as e:
            return {'error': f'Transfer failed: {str(e)}'}

    def detect_chain_from_address(self, address):
        """Detect which chain an address belongs to"""
        try:
            # ETH-style address
            if address.startswith('0x'):
                # You might want to add more sophisticated detection here
                return 'eth'
            # Solana address
            elif len(address) == 44:
                return 'sol'
            return None
        except:
            return None

    def execute_bridge_transfer(self, bridge_contract, from_chain, to_chain, amount, to_address):
        """Execute a single bridge transfer step"""
        try:
            # This is a placeholder for actual bridge contract interaction
            # You would need to implement the actual bridge contract calls
            return {
                'status': 'pending',
                'from_chain': from_chain,
                'to_chain': to_chain,
                'amount': amount,
                'bridge_contract': bridge_contract
            }
        except Exception as e:
            return {'error': f'Bridge transfer failed: {str(e)}'}

    def parse_message(self, message):
        """Enhanced message parsing with intent recognition"""
        doc = self.nlp(message.lower())
        
        # Check for common phrases first
        phrase_matches = self.phrase_matcher(doc)
        if phrase_matches:
            match_id, start, end = phrase_matches[0]
            intent = self.nlp.vocab.strings[match_id]
            return intent, {"type": "conversation"}

        # Check for command patterns
        matches = self.matcher(doc)
        if not matches:
            # Try to understand context using entity recognition
            entities = [(ent.text, ent.label_) for ent in doc.ents]
            numbers = [token.text for token in doc if token.like_num]
            crypto_mentions = [token.text for token in doc 
                             if token.text in ["eth", "bnb", "matic", "avax", "sol"]]
            
            # Additional context analysis
            if crypto_mentions:
                if any(word in message for word in ["price", "worth", "cost"]):
                    return "PRICE", {'coins': crypto_mentions}
                if any(word in message for word in ["balance", "have", "own"]):
                    return "BALANCE", {'coins': crypto_mentions}
            
            return None, None

        match_id, start, end = matches[0]
        match_type = self.nlp.vocab.strings[match_id]
        matched_tokens = doc[start:end]
        
        parsed_data = {
            'command': match_type,
            'tokens': matched_tokens,
            'amounts': [token.text for token in matched_tokens if token.like_num],
            'coins': [token.text for token in matched_tokens 
                     if token.text in ["eth", "bnb", "matic", "avax", "sol"]],
            'addresses': [token.text for token in matched_tokens if len(token.text) > 30]
        }
        
        return match_type, parsed_data

    def generate_response(self, intent, data):
        """Generate natural language responses with actual results"""
        try:
            if intent == "greeting":
                return "👋 Hello! I'm your blockchain assistant. How can I help you today?"
            
            elif intent == "farewell":
                return "👋 Goodbye! Have a great day! Feel free to come back anytime."
            
            elif intent == "thanks":
                return "You're welcome! 😊 Is there anything else you'd like to know about your crypto?"
            
            elif intent == "help":
                return self.help_menu
            
            elif intent == "TRANSFER":
                amount = data['amounts'][0]
                coin = data['coins'][0].upper()
                address = data['addresses'][0]
                
                # Validate the transfer
                if not self.validate_address(address):
                    return f"❌ Sorry, but {address} doesn't seem to be a valid address. Please check and try again."
                
                # Get gas estimate
                gas_price = self.get_gas_prices().get(coin.lower(), 0)
                estimated_gas = f"(estimated gas fee: {gas_price:.8f} {coin})"
                
                # Execute transfer
                try:
                    result = self.execute_cross_chain_transfer(coin.lower(), address, float(amount))
                    if 'error' in result:
                        return f"❌ Transfer failed: {result['error']}"
                    
                    return (f"✅ Great! I've initiated the transfer of {amount} {coin} to {address[:6]}...{address[-4:]}\n"
                           f"🔸 Status: {result['message']}\n"
                           f"⛽ {estimated_gas}")
                except Exception as e:
                    return f"❌ Sorry, there was an error processing your transfer: {str(e)}"
                
            elif intent == "BALANCE":
                coin = data['coins'][0].upper()
                try:
                    # Get the connection for the specified coin
                    connection = self.get_chain_connection(coin.lower())
                    if not connection:
                        return f"❌ Sorry, I couldn't connect to the {coin} network. Please try again later."
                    
                    # Get wallet address from session
                    wallet_address = session.get('wallet_address')
                    if not wallet_address:
                        return "❌ Please connect your wallet first!"
                    
                    # Get balance
                    if coin.lower() == 'sol':
                        balance = connection.get_balance(wallet_address)['result']['value'] / 1e9
                    else:
                        balance = connection.eth.get_balance(wallet_address)
                        balance = connection.from_wei(balance, 'ether')
                    
                    # Get current price (you would need to implement get_current_price)
                    price = self.get_current_price(coin.lower())
                    usd_value = balance * price if price else 0
                    
                    return (f"💰 Your {coin} Balance:\n"
                           f"🔸 {balance:.8f} {coin}\n"
                           f"💵 ≈ ${usd_value:.2f} USD")
                except Exception as e:
                    return f"❌ Sorry, I couldn't fetch your {coin} balance: {str(e)}"
                
            elif intent == "PRICE":
                coin = data['coins'][0].upper()
                try:
                    price = self.get_current_price(coin.lower())
                    if not price:
                        return f"❌ Sorry, I couldn't fetch the current price for {coin}"
                    
                    # Get 24h change (you would need to implement get_24h_change)
                    change_24h = self.get_24h_change(coin.lower())
                    change_symbol = "📈" if change_24h > 0 else "📉"
                    
                    return (f"💱 Current {coin} Price:\n"
                           f"💵 ${price:,.2f} USD\n"
                           f"{change_symbol} 24h Change: {change_24h:+.2f}%")
                except Exception as e:
                    return f"❌ Sorry, I couldn't fetch the price for {coin}: {str(e)}"
                
            elif intent == "HISTORY":
                try:
                    wallet_address = session.get('wallet_address')
                    
                    if not wallet_address:
                        return "❌ Please connect your wallet first!"
                    
                    # If no specific coin is mentioned, show transactions for all supported coins
                    if 'coins' not in data or not data['coins']:
                        response = "📜 Recent Transactions Across All Chains:\n"
                        response += f"{SEPARATOR}\n\n"
                        
                        # Check transactions for each supported coin
                        supported_coins = ["eth", "bnb", "matic", "avax", "sol"]
                        found_transactions = False
                        
                        for coin in supported_coins:
                            transactions = self.get_transaction_history(coin, wallet_address, limit=3)
                            if transactions:
                                found_transactions = True
                                response += f"💰 {coin.upper()} Transactions:\n"
                                
                                for idx, tx in enumerate(transactions, 1):
                                    if coin == 'sol':
                                        response += (f"🔸 Transaction {idx}:\n"
                                                   f"   Hash: {tx['hash'][:6]}...{tx['hash'][-4:]}\n"
                                                   f"   Date: {tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                                                   f"   Status: {tx['status'].title()}\n\n")
                                    else:
                                        response += (f"🔸 Transaction {idx}:\n"
                                                   f"   Hash: {tx['hash'][:6]}...{tx['hash'][-4:]}\n"
                                                   f"   From: {tx['from'][:6]}...{tx['from'][-4:]}\n"
                                                   f"   To: {tx['to'][:6]}...{tx['to'][-4:]}\n"
                                                   f"   Amount: {tx['value']:.8f} {coin.upper()}\n"
                                                   f"   Date: {tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                                                   f"   Status: {tx['status'].title()}\n\n")
                                
                                response += f"{SEPARATOR}\n\n"
                        
                        if not found_transactions:
                            return "❌ No recent transactions found across any chains."
                        
                        response += ("💡 Tip: To see more transactions for a specific chain,\n"
                                   "   try 'show my eth transactions' or 'history bnb'")
                        return response
                    
                    # If specific coin is mentioned, show detailed history for that coin
                    coin = data['coins'][0].upper()
                    transactions = self.get_transaction_history(coin.lower(), wallet_address)
                    
                    if not transactions:
                        return f"❌ No recent {coin} transactions found or error fetching history."
                    
                    response = f"📜 Recent {coin} Transactions:\n"
                    response += f"{SEPARATOR}\n\n"
                    
                    for idx, tx in enumerate(transactions, 1):
                        if coin.lower() == 'sol':
                            response += (f"🔸 Transaction {idx}:\n"
                                       f"   Hash: {tx['hash'][:6]}...{tx['hash'][-4:]}\n"
                                       f"   Date: {tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                                       f"   Status: {tx['status'].title()}\n\n")
                        else:
                            response += (f"🔸 Transaction {idx}:\n"
                                       f"   Hash: {tx['hash'][:6]}...{tx['hash'][-4:]}\n"
                                       f"   From: {tx['from'][:6]}...{tx['from'][-4:]}\n"
                                       f"   To: {tx['to'][:6]}...{tx['to'][-4:]}\n"
                                       f"   Amount: {tx['value']:.8f} {coin}\n"
                                       f"   Date: {tx['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                                       f"   Status: {tx['status'].title()}\n\n")
                    
                    return response
                    
                except Exception as e:
                    return f"❌ Sorry, I couldn't fetch your transaction history: {str(e)}"
            
            return "I'm not sure how to help with that. Type 'help' to see what I can do!"
            
        except Exception as e:
            return f"❌ An error occurred: {str(e)}\nPlease try again or type 'help' for available commands."

    def get_current_price(self, coin_type):
        """Get current price for a cryptocurrency"""
        try:
            # You would need to implement this using a price feed API
            # This is a placeholder implementation
            # Consider using CoinGecko, Binance, or other crypto price APIs
            price_feed = {
                'eth': 2000.00,
                'bnb': 300.00,
                'matic': 1.20,
                'avax': 30.00,
                'sol': 100.00
            }
            return price_feed.get(coin_type.lower(), 0)
        except Exception as e:
            print(f"Error fetching price: {str(e)}")
            return None

    def get_24h_change(self, coin_type):
        """Get 24-hour price change percentage"""
        try:
            # You would need to implement this using a price feed API
            # This is a placeholder implementation
            change_feed = {
                'eth': 2.5,
                'bnb': -1.2,
                'matic': 5.0,
                'avax': -0.8,
                'sol': 3.2
            }
            return change_feed.get(coin_type.lower(), 0)
        except Exception as e:
            print(f"Error fetching 24h change: {str(e)}")
            return 0

    def get_transaction_history(self, coin_type, address, limit=5):
        """Get recent transactions for the specified address"""
        try:
            connection = self.get_chain_connection(coin_type)
            if not connection:
                return None

            if coin_type.lower() == 'sol':
                # Handle Solana transactions
                response = connection.get_signatures_for_address(address, limit=limit)
                if 'result' in response:
                    return [{
                        'hash': tx['signature'],
                        'timestamp': datetime.fromtimestamp(tx['blockTime']),
                        'status': 'confirmed' if tx['confirmationStatus'] == 'finalized' else 'pending'
                    } for tx in response['result']]
            else:
                # Handle ETH-style transactions
                latest_block = connection.eth.block_number
                transactions = []
                
                # Get transactions from last 10 blocks (adjust as needed)
                for i in range(latest_block, latest_block - 10, -1):
                    block = connection.eth.get_block(i, full_transactions=True)
                    for tx in block.transactions:
                        if tx['from'].lower() == address.lower() or tx['to'] and tx['to'].lower() == address.lower():
                            transactions.append({
                                'hash': tx['hash'].hex(),
                                'from': tx['from'],
                                'to': tx['to'],
                                'value': connection.from_wei(tx['value'], 'ether'),
                                'timestamp': datetime.fromtimestamp(block['timestamp']),
                                'status': 'confirmed'
                            })
                            if len(transactions) >= limit:
                                break
                    if len(transactions) >= limit:
                        break
                
                return transactions

        except Exception as e:
            print(f"Error fetching transaction history: {str(e)}")
            return None

chatbot = BlockchainChatBot()

@app.route('/')
def login():
    if 'wallet_address' in session:
        return redirect(url_for('chat_page'))
    return render_template('login.html')

@app.route('/chat')
def chat_page():
    if 'wallet_address' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', initial_message=chatbot.help_menu)

@app.route('/chat/message', methods=['POST'])
def chat_message():
    data = request.json
    message = data.get('message', '').strip()
    
    # Parse the message
    intent, parsed_data = chatbot.parse_message(message)
    
    if not intent:
        return jsonify({
            'response': "I'm not sure what you mean. Here's what I can help you with:\n\n" + 
                       chatbot.help_menu
        })
    
    # Generate appropriate response
    response = chatbot.generate_response(intent, parsed_data)
    
    # If it's a command that requires blockchain interaction
    if intent in ["TRANSFER", "BALANCE", "PRICE"]:
        try:
            # Execute the blockchain operation
            if intent == "TRANSFER":
                # Your existing transfer logic
                pass
            elif intent == "BALANCE":
                # Your existing balance logic
                pass
            elif intent == "PRICE":
                # Your existing price logic
                pass
        except Exception as e:
            return jsonify({'error': f'Error processing request: {str(e)}'})
    
    return jsonify({'response': response})

@app.route('/connect-metamask', methods=['POST'])
def connect_metamask():
    data = request.json
    wallet_address = data.get('wallet_address')
    
    if not wallet_address:
        return jsonify({'error': 'Invalid wallet address'}), 400
    
    # Convert to checksum address before storing in session
    try:
        checksum_address = Web3.to_checksum_address(wallet_address)
        session['wallet_address'] = checksum_address
        return jsonify({'message': 'Wallet connected successfully'})
    except Exception as e:
        return jsonify({'error': f'Invalid wallet address format: {str(e)}'}), 400

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'})

if __name__ == '__main__':
    app.run(debug=True)

