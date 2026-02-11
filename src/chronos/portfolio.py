"""
Portfolio 資產組合追蹤模組

追蹤每位投資者的:
- USD 餘額
- BTC 持倉
- 歷史淨值變化
- 交易記錄
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """持倉資料結構"""
    symbol: str  # 資產代號 (BTC)
    quantity: float  # 持有數量
    avg_cost: float  # 平均成本
    
    @property
    def cost_basis(self) -> float:
        """成本基礎 (總投入)"""
        return self.quantity * self.avg_cost
    
    def update(self, quantity_delta: float, price: float):
        """
        更新持倉
        
        Args:
            quantity_delta: 數量變化 (正數買入，負數賣出)
            price: 交易價格
        """
        if quantity_delta > 0:
            # 買入：更新平均成本
            total_cost = self.cost_basis + (quantity_delta * price)
            self.quantity += quantity_delta
            if self.quantity > 0:
                self.avg_cost = total_cost / self.quantity
        else:
            # 賣出：數量減少，平均成本不變
            self.quantity += quantity_delta  # quantity_delta 是負數
            if self.quantity <= 0:
                self.quantity = 0
                self.avg_cost = 0


@dataclass
class PortfolioSnapshot:
    """資產組合快照"""
    date: str
    usd_balance: float
    btc_quantity: float
    btc_price: float
    total_value_usd: float
    daily_return_pct: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "usd_balance": round(self.usd_balance, 2),
            "btc_quantity": round(self.btc_quantity, 8),
            "btc_price": round(self.btc_price, 2),
            "total_value_usd": round(self.total_value_usd, 2),
            "daily_return_pct": round(self.daily_return_pct, 4),
        }


@dataclass
class TradeRecord:
    """交易記錄"""
    date: str
    action: str  # BUY, SELL, HOLD
    symbol: str
    quantity: float
    price: float
    usd_amount: float
    reason: str
    portfolio_value_after: float
    
    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "action": self.action,
            "symbol": self.symbol,
            "quantity": round(self.quantity, 8),
            "price": round(self.price, 2),
            "usd_amount": round(self.usd_amount, 2),
            "reason": self.reason,
            "portfolio_value_after": round(self.portfolio_value_after, 2),
        }


class Portfolio:
    """
    投資組合管理器
    
    追蹤單一投資者的資產狀態，包括：
    - USD 現金餘額
    - BTC 持倉
    - 歷史淨值曲線
    - 完整交易記錄
    """
    
    def __init__(
        self,
        investor_id: str,
        initial_capital: float = 1_000_000.0,
    ):
        """
        初始化投資組合
        
        Args:
            investor_id: 投資者識別碼
            initial_capital: 初始資金 (USD)
        """
        self.investor_id = investor_id
        self.initial_capital = initial_capital
        self.usd_balance = initial_capital
        self.btc_position = Position(symbol="BTC", quantity=0.0, avg_cost=0.0)
        
        # 歷史記錄
        self.snapshots: list[PortfolioSnapshot] = []
        self.trades: list[TradeRecord] = []
        
        logger.info(f"[{investor_id}] 初始化投資組合: ${initial_capital:,.2f}")
    
    def get_total_value(self, btc_price: float) -> float:
        """
        計算總資產價值
        
        Args:
            btc_price: 當前 BTC 價格
            
        Returns:
            float: 總資產價值 (USD)
        """
        btc_value = self.btc_position.quantity * btc_price
        return self.usd_balance + btc_value
    
    def get_return_pct(self, btc_price: float) -> float:
        """
        計算總報酬率
        
        Args:
            btc_price: 當前 BTC 價格
            
        Returns:
            float: 報酬率 (百分比)
        """
        total_value = self.get_total_value(btc_price)
        return ((total_value - self.initial_capital) / self.initial_capital) * 100
    
    def buy(
        self,
        date: str,
        btc_price: float,
        usd_amount: float,
        reason: str = "",
    ) -> bool:
        """
        買入 BTC
        
        Args:
            date: 交易日期
            btc_price: BTC 價格
            usd_amount: 買入金額 (USD)
            reason: 交易理由
            
        Returns:
            bool: 交易是否成功
        """
        # 檢查餘額
        if usd_amount > self.usd_balance:
            logger.warning(
                f"[{self.investor_id}] 餘額不足: "
                f"需要 ${usd_amount:,.2f}, 可用 ${self.usd_balance:,.2f}"
            )
            usd_amount = self.usd_balance  # 使用全部可用餘額
        
        if usd_amount <= 0:
            logger.warning(f"[{self.investor_id}] 無法買入: 金額為 0")
            return False
        
        # 計算買入數量
        btc_quantity = usd_amount / btc_price
        
        # 更新餘額與持倉
        self.usd_balance -= usd_amount
        self.btc_position.update(btc_quantity, btc_price)
        
        # 記錄交易
        portfolio_value = self.get_total_value(btc_price)
        trade = TradeRecord(
            date=date,
            action="BUY",
            symbol="BTC",
            quantity=btc_quantity,
            price=btc_price,
            usd_amount=usd_amount,
            reason=reason,
            portfolio_value_after=portfolio_value,
        )
        self.trades.append(trade)
        
        logger.info(
            f"[{self.investor_id}] 買入 {btc_quantity:.6f} BTC @ ${btc_price:,.2f} "
            f"(${usd_amount:,.2f})"
        )
        return True
    
    def sell(
        self,
        date: str,
        btc_price: float,
        btc_quantity: float,
        reason: str = "",
    ) -> bool:
        """
        賣出 BTC
        
        Args:
            date: 交易日期
            btc_price: BTC 價格
            btc_quantity: 賣出數量
            reason: 交易理由
            
        Returns:
            bool: 交易是否成功
        """
        # 檢查持倉
        if btc_quantity > self.btc_position.quantity:
            logger.warning(
                f"[{self.investor_id}] 持倉不足: "
                f"需要 {btc_quantity:.6f} BTC, 持有 {self.btc_position.quantity:.6f} BTC"
            )
            btc_quantity = self.btc_position.quantity  # 賣出全部持倉
        
        if btc_quantity <= 0:
            logger.warning(f"[{self.investor_id}] 無法賣出: 數量為 0")
            return False
        
        # 計算賣出金額
        usd_amount = btc_quantity * btc_price
        
        # 更新餘額與持倉
        self.usd_balance += usd_amount
        self.btc_position.update(-btc_quantity, btc_price)
        
        # 記錄交易
        portfolio_value = self.get_total_value(btc_price)
        trade = TradeRecord(
            date=date,
            action="SELL",
            symbol="BTC",
            quantity=btc_quantity,
            price=btc_price,
            usd_amount=usd_amount,
            reason=reason,
            portfolio_value_after=portfolio_value,
        )
        self.trades.append(trade)
        
        logger.info(
            f"[{self.investor_id}] 賣出 {btc_quantity:.6f} BTC @ ${btc_price:,.2f} "
            f"(${usd_amount:,.2f})"
        )
        return True
    
    def hold(self, date: str, btc_price: float, reason: str = ""):
        """
        記錄持有 (不操作)
        
        Args:
            date: 日期
            btc_price: BTC 價格
            reason: 理由
        """
        portfolio_value = self.get_total_value(btc_price)
        trade = TradeRecord(
            date=date,
            action="HOLD",
            symbol="BTC",
            quantity=0,
            price=btc_price,
            usd_amount=0,
            reason=reason,
            portfolio_value_after=portfolio_value,
        )
        self.trades.append(trade)
        
        logger.debug(f"[{self.investor_id}] 持有不動 @ ${btc_price:,.2f}")
    
    def take_snapshot(self, date: str, btc_price: float):
        """
        記錄當日資產快照
        
        Args:
            date: 日期
            btc_price: BTC 價格
        """
        total_value = self.get_total_value(btc_price)
        
        # 計算日報酬率
        daily_return = 0.0
        if self.snapshots:
            prev_value = self.snapshots[-1].total_value_usd
            if prev_value > 0:
                daily_return = ((total_value - prev_value) / prev_value) * 100
        
        snapshot = PortfolioSnapshot(
            date=date,
            usd_balance=self.usd_balance,
            btc_quantity=self.btc_position.quantity,
            btc_price=btc_price,
            total_value_usd=total_value,
            daily_return_pct=daily_return,
        )
        self.snapshots.append(snapshot)
        
        logger.debug(
            f"[{self.investor_id}] 快照 {date}: "
            f"${total_value:,.2f} ({daily_return:+.2f}%)"
        )
    
    def get_summary(self, btc_price: float) -> dict:
        """取得投資組合摘要"""
        total_value = self.get_total_value(btc_price)
        return_pct = self.get_return_pct(btc_price)
        
        return {
            "investor_id": self.investor_id,
            "initial_capital": self.initial_capital,
            "current_value": round(total_value, 2),
            "return_pct": round(return_pct, 2),
            "usd_balance": round(self.usd_balance, 2),
            "btc_quantity": round(self.btc_position.quantity, 8),
            "btc_avg_cost": round(self.btc_position.avg_cost, 2),
            "total_trades": len([t for t in self.trades if t.action != "HOLD"]),
        }
    
    def export_trades_csv(self) -> str:
        """
        導出交易記錄為 CSV 格式
        
        Returns:
            str: CSV 內容
        """
        lines = ["date,action,symbol,quantity,price,usd_amount,reason,portfolio_value"]
        
        for trade in self.trades:
            # 清理 reason 中的逗號和換行
            reason = trade.reason.replace(",", ";").replace("\n", " ")[:100]
            lines.append(
                f"{trade.date},{trade.action},{trade.symbol},"
                f"{trade.quantity:.8f},{trade.price:.2f},{trade.usd_amount:.2f},"
                f'"{reason}",{trade.portfolio_value_after:.2f}'
            )
        
        return "\n".join(lines)
