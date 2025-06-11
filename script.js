// Global variable to track wallet connection status
let isWalletConnected = false;

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Handle logout
    document.getElementById('logout-button').addEventListener('click', async () => {
        try {
            const response = await fetch('/logout', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                window.location.href = '/';
            } else {
                console.error('Logout failed');
            }
        } catch (error) {
            console.error('Error during logout:', error);
        }
    });

    // Handle chat form submission
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatMessages = document.getElementById('chat-messages');

    chatForm.addEventListener('submit', async function(event) {
        // Prevent the form from submitting normally
        event.preventDefault();
        
        const message = userInput.value.trim();
        if (!message) return;

        // Display user message
        const userMessageDiv = document.createElement('div');
        userMessageDiv.className = 'user-message';
        userMessageDiv.textContent = message;
        chatMessages.appendChild(userMessageDiv);

        // Clear input
        userInput.value = '';

        try {
            const response = await fetch('/chat/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message: message })
            });
            
            const data = await response.json();
            
            // Display bot response
            const botMessageDiv = document.createElement('div');
            botMessageDiv.className = 'bot-message';
            
            if (data.error) {
                botMessageDiv.textContent = data.error;
            } else {
                if (message.toLowerCase() === 'help' || (data.response && data.response.includes('═'))) {
                    const preElement = document.createElement('pre');
                    preElement.textContent = data.response;
                    botMessageDiv.appendChild(preElement);
                } else {
                    botMessageDiv.textContent = data.response;
                }
            }
            
            chatMessages.appendChild(botMessageDiv);
            
            // Scroll to bottom
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } catch (error) {
            console.error('Error:', error);
            const errorDiv = document.createElement('div');
            errorDiv.className = 'bot-message error';
            errorDiv.textContent = 'Sorry, something went wrong. Please try again.';
            chatMessages.appendChild(errorDiv);
        }
    });

    // Initial scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
});

document.getElementById('connect-wallet').addEventListener('click', async function() {
    try {
        const walletAddress = prompt("Please enter your wallet address:");
        
        if (!walletAddress) return;

        const response = await fetch('/connect-wallet', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ wallet_address: walletAddress })
        });

        const data = await response.json();

        if (response.ok) {
            isWalletConnected = true;
            this.textContent = 'Wallet Connected';
            this.classList.add('connected');
            
            // Enable input field
            document.getElementById('user-input').disabled = false;
            document.querySelector('#chat-form button').disabled = false;
            
            // Display success message in chat
            const chatMessages = document.getElementById('chat-messages');
            const botMessageDiv = document.createElement('div');
            botMessageDiv.className = 'bot-message';
            botMessageDiv.textContent = data.message;
            chatMessages.appendChild(botMessageDiv);
        } else {
            alert(data.error);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to connect wallet. Please try again.');
    }
}); 