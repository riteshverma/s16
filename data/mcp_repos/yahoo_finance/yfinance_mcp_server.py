import os
import json
import logging
from datetime import datetime
from typing import Any, Sequence, Dict, List, Optional, Union
from collections.abc import Sequence as SequenceABC

import yfinance as yf
from mcp.server import Server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from pydantic import AnyUrl

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yfinance-mcp-server")

# Default settings
DEFAULT_SYMBOLS = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]

app = Server("yfinance-mcp-server")

async def fetch_stock_info(symbol: str) -> dict[str, Any]:
    """Fetch current stock information."""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        return info
    except Exception as e:
        logger.error(f"Error fetching stock info for {symbol}: {str(e)}")
        raise RuntimeError(f"Failed to fetch stock info: {str(e)}")
    
@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available financial resources."""
    resources = []
    
    # Add default stock resources
    for symbol in DEFAULT_SYMBOLS:
        uri = AnyUrl(f"finance://{symbol}/info")
        resources.append(
            Resource(
                uri=uri,
                name=f"Current stock information for {symbol}",
                mimeType="application/json",
                description=f"Real-time market data for {symbol}"
            )
        )
    
    return resources

@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read current stock information."""
    uri_str = str(uri)
    
    if uri_str.startswith("finance://") and uri_str.endswith("/info"):
        parts = uri_str.split("/")
        if len(parts) >= 3:
            symbol = parts[-2]
            try:
                stock_data = await fetch_stock_info(symbol)
                return json.dumps(stock_data, indent=2)
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {str(e)}")
                raise RuntimeError(f"Failed to read resource: {str(e)}")
    
    raise ValueError(f"Unknown resource: {uri}")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available financial tools."""
    return [
        Tool(
            name="get_stock_price",
            description="Get the current stock price for a given symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., AAPL, MSFT, GOOG)"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="get_historical_data",
            description="Get historical stock data for a symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., AAPL, MSFT, GOOG)"
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)",
                        "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"],
                        "default": "1mo"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="get_stock_metric",
            description="""Get a specific metric for a stock using yfinance field names.
            Common requests and their exact field names:
            
            Stock Price & Trading Info:
            - Current/Stock Price: currentPrice
            - Opening Price: open
            - Day's High: dayHigh
            - Day's Low: dayLow
            - Previous Close: previousClose
            - 52 Week High: fiftyTwoWeekHigh
            - 52 Week Low: fiftyTwoWeekLow
            - 50 Day Average: fiftyDayAverage
            - 200 Day Average: twoHundredDayAverage
            - Trading Volume: volume
            - Average Volume: averageVolume
            - Average Daily Volume (10 day): averageDailyVolume10Day
            - Market Cap/Capitalization: marketCap
            - Beta: beta
            - Bid Price: bid
            - Ask Price: ask
            - Bid Size: bidSize
            - Ask Size: askSize
            
            Company Information:
            - Company Name: longName
            - Short Name: shortName
            - Business Description/About/Summary: longBusinessSummary
            - Industry: industry
            - Sector: sector
            - Website: website
            - Number of Employees: fullTimeEmployees
            - Country: country
            - State: state
            - City: city
            - Address: address1
            
            Financial Metrics:
            - PE Ratio: trailingPE
            - Forward PE: forwardPE
            - Price to Book: priceToBook
            - Price to Sales: priceToSalesTrailing12Months
            - Enterprise Value: enterpriseValue
            - Enterprise to EBITDA: enterpriseToEbitda
            - Enterprise to Revenue: enterpriseToRevenue
            - Book Value: bookValue
            
            Earnings & Revenue:
            - Revenue/Total Revenue: totalRevenue
            - Revenue Growth: revenueGrowth
            - Revenue Per Share: revenuePerShare
            - EBITDA: ebitda
            - EBITDA Margins: ebitdaMargins
            - Net Income: netIncomeToCommon
            - Earnings Growth: earningsGrowth
            - Quarterly Earnings Growth: earningsQuarterlyGrowth
            - Forward EPS: forwardEps
            - Trailing EPS: trailingEps
            
            Margins & Returns:
            - Profit Margin: profitMargins
            - Operating Margin: operatingMargins
            - Gross Margins: grossMargins
            - Return on Equity/ROE: returnOnEquity
            - Return on Assets/ROA: returnOnAssets
            
            Dividends:
            - Dividend Yield: dividendYield
            - Dividend Rate: dividendRate
            - Dividend Date: lastDividendDate
            - Ex-Dividend Date: exDividendDate
            - Payout Ratio: payoutRatio
            
            Balance Sheet:
            - Total Cash: totalCash
            - Cash Per Share: totalCashPerShare
            - Total Debt: totalDebt
            - Debt to Equity: debtToEquity
            - Current Ratio: currentRatio
            - Quick Ratio: quickRatio
            
            Ownership:
            - Institutional Ownership: heldPercentInstitutions
            - Insider Ownership: heldPercentInsiders
            - Float Shares: floatShares
            - Shares Outstanding: sharesOutstanding
            - Short Ratio: shortRatio
            
            Analyst Coverage:
            - Analyst Recommendation: recommendationKey
            - Number of Analysts: numberOfAnalystOpinions
            - Price Target Mean: targetMeanPrice
            - Price Target High: targetHighPrice
            - Price Target Low: targetLowPrice
            - Price Target Median: targetMedianPrice
            
            Risk Metrics:
            - Overall Risk: overallRisk
            - Audit Risk: auditRisk
            - Board Risk: boardRisk
            - Compensation Risk: compensationRisk
            
            Other:
            - Currency: currency
            - Exchange: exchange
            - Year Change/52 Week Change: 52WeekChange
            - S&P 500 Year Change: SandP52WeekChange""",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., AAPL, MSFT, GOOG)"
                    },
                    "metric": {
                        "type": "string",
                        "description": "The metric to retrieve, use camelCase"
                    }
                },
                "required": ["symbol", "metric"]
            }
        ),
        Tool(
            name="compare_stocks",
            description="Compare multiple stocks by a specific metric",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of stock symbols to compare"
                    },
                    "metric": {
                        "type": "string",
                        "description": "Metric to compare (e.g., currentPrice, marketCap)"
                    }
                },
                "required": ["symbols", "metric"]
            }
        ),
        Tool(
            name="search_stocks",
            description="Search for stocks by company name or keyword",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (company name or keyword)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    
    try:
        if name == "get_stock_price":
            symbol = arguments["symbol"]
            stock = yf.Ticker(symbol)
            
            # Try to get the most recent price
            history = stock.history(period="1d")
            
            if not history.empty:
                price = history['Close'].iloc[-1]
            else:
                # Fallback to info
                info = stock.info
                price = info.get("currentPrice", info.get("regularMarketPrice", None))
            
            if price is None:
                return [TextContent(type="text", text=f"Could not retrieve price for {symbol}")]
            
            return [TextContent(
                type="text", 
                text=f"The current price of {symbol} is ${price:.2f}"
            )]
            
        elif name == "get_stock_metric":
            symbol = arguments["symbol"]
            metric = arguments["metric"]
            
            stock_data = await fetch_stock_info(symbol)
            
            if metric in stock_data:
                # Format different metrics appropriately
                value = stock_data[metric]
                formatted_value = value
                
                # Format percentages
                if metric in ["dividendYield", "profitMargins", "operatingMargins", "grossMargins"]:
                    if value is not None:
                        formatted_value = f"{value * 100:.2f}%"
                
                # Format currency values
                elif metric in ["currentPrice", "open", "dayHigh", "dayLow", "targetMeanPrice"]:
                    if value is not None:
                        formatted_value = f"${value:.2f}"
                
                # Format large numbers
                elif metric in ["marketCap", "totalRevenue", "volume"]:
                    if value is not None:
                        formatted_value = f"{value:,}"
                
                return [TextContent(
                    type="text",
                    text=f"{symbol} {metric}: {formatted_value}"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Metric '{metric}' not found for {symbol}"
                )]
                
        elif name == "get_historical_data":
            symbol = arguments["symbol"]
            period = arguments.get("period", "1mo")

            stock = yf.Ticker(symbol)
            history = stock.history(period=period)
            
            if history.empty:
                return [TextContent(
                    type="text",
                    text=f"No historical data available for {symbol} with period {period}"
                )]
            
            data = []
            for date, row in history.iterrows():
                data.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "open": row["Open"],
                    "high": row["High"],
                    "low": row["Low"],
                    "close": row["Close"],
                    "volume": row["Volume"]
                })

            return [TextContent(
                type="text",
                text=json.dumps(data, indent=2)
            )]
        
        elif name == "compare_stocks":
            symbols = arguments["symbols"]
            metric = arguments["metric"]
            
            results = {}
            for symbol in symbols:
                try:
                    stock_data = await fetch_stock_info(symbol)
                    if metric in stock_data:
                        results[symbol] = stock_data[metric]
                    else:
                        results[symbol] = f"Metric '{metric}' not found"
                except Exception as e:
                    results[symbol] = f"Error: {str(e)}"
            
            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )]
        
        elif name == "search_stocks":
            query = arguments["query"]
            limit = arguments.get("limit", 5)
            
            # Use yfinance search functionality
            from yfinance.search import Search
            search_results = Search(query=query, max_results=limit)
            
            results = {}
            if search_results.quotes:
                results["quotes"] = []
                for quote in search_results.quotes[:limit]:
                    results["quotes"].append({
                        "symbol": quote.get("symbol"),
                        "name": quote.get("shortname", quote.get("longname")),
                        "exchange": quote.get("exchange"),
                        "price": quote.get("regularMarketPrice")
                    })
            
            if search_results.news:
                results["news"] = []
                for news in search_results.news[:limit]:
                    results["news"].append({
                        "title": news.get("title"),
                        "publisher": news.get("publisher"),
                        "link": news.get("link")
                    })
            
            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )]
        
        else:
            return [TextContent(
                type="text",
                text=f"Unknown tool: {name}"
            )]
            
    except Exception as e:
        logger.error(f"Error in call_tool: {str(e)}")
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]

async def main():
    """Run the server."""
    from mcp.server.stdio import stdio_server

    logger.info("Starting yfinance MCP server...")
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
