from django.urls import path

from modules.leave.views import (
    AdjustBalanceView, AuthorityDetailView, AuthorityView, CalendarDatesView,
    CalendarView, DecisionView, LedgerView, MineView, OfflineRecordView,
    PublishCalendarView, ReplaceSubstituteView, RequestCancelView, RequestCreateView, RequestListView,
    RelatedRequestView, TypesView, VacationPeriodView, WorkflowConfigView,
)

urlpatterns = [
    path("mine", MineView.as_view()),
    path("requests", RequestListView.as_view()),
    path("requests/create", RequestCreateView.as_view()),
    path("requests/<int:pk>/cancel", RequestCancelView.as_view()),
    path("requests/<int:pk>/substitute", ReplaceSubstituteView.as_view()),
    path("requests/<int:pk>/decision", DecisionView.as_view()),
    path("requests/<int:pk>/related", RelatedRequestView.as_view()),
    path("requests/offline", OfflineRecordView.as_view()),
    path("calendars", CalendarView.as_view()),
    path("calendars/<int:pk>/dates", CalendarDatesView.as_view()),
    path("calendars/<int:pk>/publish", PublishCalendarView.as_view()),
    path("vacation-periods", VacationPeriodView.as_view()),
    path("authorities", AuthorityView.as_view()),
    path("authorities/<int:pk>", AuthorityDetailView.as_view()),
    path("workflow-config", WorkflowConfigView.as_view()),
    path("types", TypesView.as_view()),
    path("types/<int:pk>", TypesView.as_view()),
    path("balances/adjust", AdjustBalanceView.as_view()),
    path("ledger", LedgerView.as_view()),
]

