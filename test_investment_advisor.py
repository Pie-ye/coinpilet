"""
測試投資顧問功能
"""
from src.agent.investment_advisor import InvestmentAdvisor
from src.chronos.personas.base import MarketContext

# 建立測試市場上下文
context = MarketContext(
    current_date='2026-02-11',
    btc_price=66500,
    btc_change_pct=-5.2,
    rsi=18.5,
    rsi_signal='oversold',
    macd_signal='bearish',
    ma_50=72000,
    ma_200=75000,
    fear_greed_value=14,
    fear_greed_label='Extreme Fear',
    news_headlines=['Bitcoin drops amid market uncertainty', 'ETF inflows continue'],
    usd_balance=1000000,
    btc_quantity=0,
)

# 取得四位投資者決策
advisor = InvestmentAdvisor()
decisions = advisor.get_multi_strategy_decisions(context)

print('=' * 60)
print('四位 AI 投資者決策結果')
print('=' * 60)
for persona_id, decision in decisions.decisions.items():
    print(f'{decision.emoji} {decision.persona_name}: {decision.action} ({decision.amount_pct}%) - {decision.reason}')
print('-' * 60)
print(f'共識: {decisions.consensus_action} (信心度: {decisions.consensus_confidence}%)')
print(f'投票: 買:{decisions.buy_votes} 賣:{decisions.sell_votes} 持有:{decisions.hold_votes}')

# 計算資金配置
allocation = advisor.calculate_portfolio_allocation(decisions, total_capital=1000000, btc_price=66500)
print('=' * 60)
print('$1,000,000 資金配置建議')
print('=' * 60)
print(f'建議行動: {allocation.recommended_action}')
print(f'買入金額: ${allocation.buy_amount_usd:,.0f}')
print(f'BTC 數量: {allocation.btc_to_buy:.4f} BTC')
print(f'風險等級: {allocation.risk_level}')
print(f'配置理由: {allocation.allocation_rationale}')

# 顯示 Markdown 表格
print('\n' + '=' * 60)
print('四位投資者決策對比表 (Markdown)')
print('=' * 60)
print(decisions.to_markdown_table())
