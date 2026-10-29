from django.urls import path

from . import views

urlpatterns = [
    path("config", views.ConfigView.as_view(), name="market-config"),
    path("symbols", views.SymbolSearchView.as_view(), name="market-symbols"),
    path("analyze", views.AnalyzeView.as_view(), name="market-analyze"),
    path("profile/<str:symbol>", views.ProfileView.as_view(), name="market-profile"),
    path("coverage/<str:symbol>", views.CoverageView.as_view(), name="market-coverage"),
    path("ingest", views.IngestView.as_view(), name="market-ingest"),
    path("chart/<str:symbol>", views.ChartView.as_view(), name="market-chart"),
    path("watchlist", views.WatchlistView.as_view(), name="market-watchlist"),
    path(
        "watchlist/<str:symbol>",
        views.WatchlistDetailView.as_view(),
        name="market-watchlist-detail",
    ),
    path("live-check", views.LiveCheckView.as_view(), name="market-live-check"),
    path("screen", views.ScreenStartView.as_view(), name="market-screen-start"),
    path("screen/latest", views.ScreenLatestView.as_view(), name="market-screen-latest"),
    path("screen/<int:pk>", views.ScreenRunView.as_view(), name="market-screen-run"),
    path("universe", views.UniverseView.as_view(), name="market-universe"),
    path("paper/tick", views.PaperTickView.as_view(), name="market-paper-tick"),
    path("paper/trades", views.PaperTradesView.as_view(), name="market-paper-trades"),
    path("paper/trades/<int:pk>/close", views.PaperCloseView.as_view(), name="market-paper-close"),
    path("paper/stats", views.PaperStatsView.as_view(), name="market-paper-stats"),
]
