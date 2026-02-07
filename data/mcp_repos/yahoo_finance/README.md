# Finance_mcp-server

A Model Context Protocol (MCP) server that provides real-time financial data to Large Language Models through Yahoo Finance.


This project creates an MCP server that allows AI models like Claude to access real-time stock and financial data through the Yahoo Finance API. The server implements the Model Context Protocol standard, enabling seamless integration with various MCP clients including Claude Desktop, Cursor, Winds AI, and others.

## 🚀 Features

- **Real-time Stock Price Lookup**: Get current prices for any publicly traded company
- **Historical Data Analysis**: Retrieve stock performance over custom time periods
- **Company Information**: Access detailed company profiles and financial metrics
- **Stock Comparison**: Compare multiple stocks based on various metrics
- **Stock Search**: Find relevant stocks by company name or keywords
- **Resource Access**: Use structured URI schemes for financial data access

## 📋 Requirements

- Python 3.9 or higher
- [yfinance](https://pypi.org/project/yfinance/) package
- [mcp](https://pypi.org/project/mcp/) package

## 💻 Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/dino65-dev/Finance_mcp-server.git
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   On Windows: venv\Scripts\activate
   ```
 Create a virtual environment (recommended) for faster creation:
   ```bash
   pip install uv
   uv venv
   On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 🔧 Usage

### Running the Server

Start the server by running:

```bash
python yfinance_mcp_server.py
```

The server will run as a stdin/stdout process that communicates via the MCP protocol.

### Integrating with MCP Clients

#### Claude Desktop

1. Open Claude Desktop
2. Go to Settings
3. Add an MCP configuration with:
   ```json
   {
     "mcpServers": {
       "yfinance": {
         "command": "python",
         "args": [
           "/absolute/path/to/yfinance_mcp_server.py"
         ]
       }
     }
   }
   ```
4. Save and restart Claude Desktop

#### Cursor

1. Open Cursor and access settings
2. Navigate to MCP section
3. Add a new global MCP server with the configuration:
   ```json
   {
     "yfinance": {
       "command": "python",
       "args": [
         "/absolute/path/to/yfinance_mcp_server.py"
       ]
     }
   }
   ```
4. Start a new chat to use the financial tools

## 📊 Available Tools

The server provides the following tools:

1. **`get_stock_price`**: Get current stock prices
   ```
   Example: Get the current price of Apple stock
   ```

2. **`get_historical_data`**: Retrieve historical price data
   ```
   Example: Get the stock history for TSLA over the past 3 months
   ```

3. **`get_stock_metric`**: Access specific financial metrics
   ```
   Example: What is Amazon's market capitalization?
   ```

4. **`compare_stocks`**: Compare multiple stocks by metrics
   ```
   Example: Compare the P/E ratios of Google, Microsoft, and Apple
   ```

5. **`search_stocks`**: Find stocks by name or keyword
   ```
   Example: Find stocks related to artificial intelligence
   ```

## 🔍 Resource URIs

Access stock information directly through resource URIs:

- `finance://SYMBOL/info` - Get basic information about a stock

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgements

- [Yahoo Finance](https://finance.yahoo.com/) for providing financial data
- [yfinance](https://github.com/ranaroussi/yfinance) for the Python API
- [Anthropic](https://modelcontextprotocol.io/introduction) for the MCP specification

## 📞 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
