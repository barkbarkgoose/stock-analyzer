from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional

from ..anchors.base import Anchor, get_anchor
from ..models import IntradayBar


class State(Enum):
    IDLE = auto()
    ARMED = auto()
    IN_TRADE = auto()
    COOLDOWN = auto()


@dataclass
class StrategyConfig:
    drop_threshold_pct: float
    rebound_confirmation_pct: float
    profit_target_pct: float
    stop_loss_pct: float
    cooldown_bars: int
    cooldown_minutes: int
    max_holding_bars: int
    end_of_day_exit: bool
    anchor_name: str = "previous_close"

    def __post_init__(self):
        if self.drop_threshold_pct <= 0:
            raise ValueError("drop_threshold_pct must be positive")
        if self.rebound_confirmation_pct <= 0:
            raise ValueError("rebound_confirmation_pct must be positive")
        if self.profit_target_pct <= 0:
            raise ValueError("profit_target_pct must be positive")
        if self.stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct must be positive")
        if self.cooldown_bars < 0:
            raise ValueError("cooldown_bars must be non-negative")
        if self.cooldown_minutes < 0:
            raise ValueError("cooldown_minutes must be non-negative")
        if self.max_holding_bars < 1:
            raise ValueError("max_holding_bars must be at least 1")


@dataclass
class Trade:
    entry_bar: int
    entry_price: float
    entry_reason: str
    exit_bar: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    pnl_pct: Optional[float] = None
    hold_bars: Optional[int] = None


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


class StateMachineBacktester:
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.anchor: Anchor = get_anchor(config.anchor_name)
        self._reset()

    def _reset(self):
        self._state = State.IDLE
        self._armed_bar: Optional[int] = None
        self._armed_price: Optional[float] = None
        self._local_low_bar: Optional[int] = None
        self._local_low_price: Optional[float] = None
        self._entry_bar: Optional[int] = None
        self._entry_price: Optional[float] = None
        self._trade: Optional[Trade] = None
        self._cooldown_remaining: int = 0
        self._hold_bars: int = 0

    def _transition_to(self, new_state: State, reason: str = ""):
        self._state = new_state

    def _check_drop_threshold(self, bar: IntradayBar, anchor_value: float) -> bool:
        drop_pct = (anchor_value - bar.low) / anchor_value * 100
        return drop_pct >= self.config.drop_threshold_pct

    def _check_rebound_confirmation(self, bar: IntradayBar) -> bool:
        if self._local_low_price is None:
            return False
        rebound_pct = (bar.close - self._local_low_price) / self._local_low_price * 100
        return rebound_pct >= self.config.rebound_confirmation_pct

    def _check_profit_target(self, bar: IntradayBar) -> bool:
        if self._entry_price is None:
            return False
        gain_pct = (bar.high - self._entry_price) / self._entry_price * 100
        return gain_pct >= self.config.profit_target_pct

    def _check_stop_loss(self, bar: IntradayBar) -> bool:
        if self._entry_price is None:
            return False
        loss_pct = (self._entry_price - bar.low) / self._entry_price * 100
        return loss_pct >= self.config.stop_loss_pct

    def _check_end_of_day(
        self, bar: IntradayBar, idx: int, bars: list[IntradayBar]
    ) -> bool:
        if not self.config.end_of_day_exit:
            return False
        if idx + 1 < len(bars):
            next_bar = bars[idx + 1]
            return next_bar.timestamp.date() != bar.timestamp.date()
        return True

    def _exit_trade(self, bar: IntradayBar, idx: int, reason: str):
        if self._trade is None or self._entry_price is None:
            return
        self._trade.exit_bar = idx
        self._trade.exit_price = bar.close
        self._trade.exit_reason = reason
        self._trade.pnl_pct = (bar.close - self._entry_price) / self._entry_price * 100
        self._trade.hold_bars = self._hold_bars
        self._trades.append(self._trade)
        self._transition_to(State.COOLDOWN, reason)
        self._cooldown_remaining = self.config.cooldown_bars
        self._trade = None
        self._entry_price = None
        self._hold_bars = 0

    def run(self, bars: list[IntradayBar]) -> BacktestResult:
        self._reset()
        self._trades: list[Trade] = []
        self._bars = bars

        for idx, bar in enumerate(bars):
            self._process_bar(bar, idx, bars)

        result = BacktestResult(trades=self._trades, metrics=self._compute_metrics())
        self._reset()
        return result

    def _process_bar(self, bar: IntradayBar, idx: int, bars: list[IntradayBar]):
        if self._state == State.IDLE:
            self._handle_idle(bar, idx)
        elif self._state == State.ARMED:
            self._handle_armed(bar, idx)
        elif self._state == State.IN_TRADE:
            self._handle_in_trade(bar, idx, bars)
        elif self._state == State.COOLDOWN:
            self._handle_cooldown(bar, idx)

    def _handle_idle(self, bar: IntradayBar, idx: int):
        try:
            anchor_value = self.anchor.get_value(self._bars, idx)
        except IndexError:
            return

        if self._check_drop_threshold(bar, anchor_value):
            self._transition_to(State.ARMED, "drop threshold hit")
            self._armed_bar = idx
            self._armed_price = bar.low
            self._local_low_bar = idx
            self._local_low_price = bar.low

    def _handle_armed(self, bar: IntradayBar, idx: int):
        if self._local_low_price is not None and bar.low < self._local_low_price:
            self._local_low_bar = idx
            self._local_low_price = bar.low

        if self._check_rebound_confirmation(bar):
            self._trade = Trade(
                entry_bar=idx,
                entry_price=bar.close,
                entry_reason=f"rebound_confirmation_from_low@{self._local_low_price:.4f}",
            )
            self._entry_bar = idx
            self._entry_price = bar.close
            self._transition_to(State.IN_TRADE, "rebound confirmed")
            self._hold_bars = 0

    def _handle_in_trade(self, bar: IntradayBar, idx: int, bars: list[IntradayBar]):
        self._hold_bars += 1

        if self._check_profit_target(bar):
            self._exit_trade(bar, idx, "profit_target")
            return

        if self._check_stop_loss(bar):
            self._exit_trade(bar, idx, "stop_loss")
            return

        if self._hold_bars >= self.config.max_holding_bars:
            self._exit_trade(bar, idx, "max_holding_bars")
            return

        if self.config.end_of_day_exit:
            if idx + 1 < len(bars):
                next_bar = bars[idx + 1]
                if next_bar.timestamp.date() != bar.timestamp.date():
                    self._exit_trade(bar, idx, "end_of_day")
                    return

    def _handle_cooldown(self, bar: IntradayBar, idx: int):
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return

        if self._cooldown_remaining == 0:
            self._transition_to(State.IDLE, "cooldown ended")
            self._cooldown_remaining = 0

    def _compute_metrics(self) -> dict:
        if not self._trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "average_pnl_pct": 0.0,
                "average_hold_bars": 0.0,
                "max_drawdown_pct": 0.0,
                "max_gain_pct": 0.0,
            }

        total = len(self._trades)
        winners = [t for t in self._trades if t.pnl_pct is not None and t.pnl_pct > 0]
        losers = [t for t in self._trades if t.pnl_pct is not None and t.pnl_pct <= 0]
        pnls = [t.pnl_pct for t in self._trades if t.pnl_pct is not None]
        hold_bars = [t.hold_bars for t in self._trades if t.hold_bars is not None]

        return {
            "total_trades": total,
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": len(winners) / total if total > 0 else 0.0,
            "average_pnl_pct": sum(pnls) / len(pnls) if pnls else 0.0,
            "average_hold_bars": sum(hold_bars) / len(hold_bars) if hold_bars else 0.0,
            "max_drawdown_pct": min(pnls) if pnls else 0.0,
            "max_gain_pct": max(pnls) if pnls else 0.0,
        }
