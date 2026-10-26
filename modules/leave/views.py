"""HTTP adapters for the ELM services; all state changes go through services."""

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasModuleGrant, HasPermission
from modules.directory import contracts as directory
from modules.leave import services
from modules.leave.models import (
    LeaveApprovalTask, LeaveAuthority, LeaveBalance, LeaveCalendar,
    LeaveCalendarDate, LeaveLedger, LeaveRequest, LeaveType,
    LeaveVacationPeriod, LeaveWorkflowConfig,
)


def _request(row, *, task=None, employee_name=""):
    return {
        "id": row.pk,
        "employee_id": row.employee_id,
        "employee_name": employee_name,
        "leave_type": row.leave_type.name,
        "leave_type_code": row.leave_type.code.upper(),
        "leave_type_id": row.leave_type_id,
        "start_date": row.start_date.isoformat(),
        "end_date": row.end_date.isoformat(),
        "days": str(row.days),
        "reason": row.reason,
        "document_url": row.document_url,
        "status": row.status,
        "reviewer_note": row.reviewer_note,
        "created_at": row.created_at.isoformat(),
        "station_leave": row.station_leave,
        "station_leave_details": row.station_leave_details,
        "substitute_id": row.substitute_id,
        "substitute_status": row.substitute_status,
        "workflow_stage": row.workflow_stage,
        "unit_head_recommendation": row.unit_head_recommendation,
        "director_self_sanction": row.director_self_sanction,
        "request_kind": row.request_kind,
        "task_id": task.pk if task else None,
        "task_action": task.action if task else "",
    }


def _role_matches(principal, task):
    if task.assigned_user_id is not None:
        return task.assigned_user_id == principal.user_id
    candidates = {str(role).strip().casefold().replace(" ", "_") for role in principal.roles}
    if principal.active_role:
        candidates.add(principal.active_role.strip().casefold().replace(" ", "_"))
    return bool(task.authority_role and task.authority_role.casefold().replace(" ", "_") in candidates)


def _may_view_all_records(principal) -> bool:
    return any(principal.has_permission(code) for code in (
        "leave.configuration.manage", "leave.balance.update", "leave.record.offline",
    ))


class LeaveView(APIView):
    permission_classes = [HasModuleGrant("leave")]


class MineView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.request.view_self")]

    def get(self, request):
        try:
            year = int(request.query_params.get("year", timezone.localdate().year))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"year": "Enter a valid calendar year."}) from exc
        if not 2000 <= year <= 2100:
            raise ValidationError({"year": "Enter a year between 2000 and 2100."})
        employee_id = request.principal.user_id
        employee = directory.get_users([employee_id]).get(employee_id)
        for leave_type in LeaveType.objects.filter(is_active=True):
            if leave_type.eligible_kinds and (not employee or employee.kind not in leave_type.eligible_kinds):
                continue
            services.balance_for(employee_id, leave_type, year)
        balances = LeaveBalance.objects.filter(employee_id=employee_id, year=year).select_related("leave_type")
        requests = LeaveRequest.objects.filter(employee_id=employee_id).select_related("leave_type")[:100]
        return Response({
            "year": year,
            "balances": [{
                "leave_type": b.leave_type.name, "leave_type_id": b.leave_type_id,
                "opening": str(b.opening), "accrued": str(b.accrued),
                "adjusted": str(b.adjusted), "used": str(b.consumed),
                "available": str(b.available),
            } for b in balances],
            "requests": [_request(r) for r in requests],
        })


class RequestCreateView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.request.create")]

    class Input(serializers.Serializer):
        leave_type_id = serializers.IntegerField(min_value=1)
        start_date = serializers.DateField()
        end_date = serializers.DateField()
        reason = serializers.CharField(max_length=1000, trim_whitespace=True)
        document_url = serializers.URLField(max_length=500, required=False, allow_blank=True)

        half_day = serializers.ChoiceField(choices=("", "first", "second"), required=False, default="")
        station_leave = serializers.BooleanField(required=False, default=False)
        station_leave_details = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
        substitute_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

    def post(self, request):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            row = services.submit_request(
                employee_id=request.principal.user_id,
                actor_id=request.principal.user_id,
                leave_type_id=values["leave_type_id"],
                start=values["start_date"], end=values["end_date"],
                reason=values["reason"], document_url=values.get("document_url", ""),
                half_day=values.get("half_day", ""),
                station_leave=values.get("station_leave", False),
                station_leave_details=values.get("station_leave_details", ""),
                substitute_id=values.get("substitute_id"),
                director_self_sanction=any(
                    str(role).strip().casefold() == "director"
                    for role in (*request.principal.roles, request.principal.active_role)
                ),
            )
        except services.LeaveError as exc:
            raise ValidationError({"leave": str(exc)}) from exc
        return Response(_request(row), status=201)


class RequestCancelView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.request.delete")]

    def post(self, request, pk):
        try:
            row = services.withdraw_request(request_id=pk, employee_id=request.principal.user_id)
        except services.LeaveError as exc:
            raise NotFound(str(exc)) from exc
        row = LeaveRequest.objects.select_related("leave_type").get(pk=row.pk)
        return Response(_request(row))


class ReplaceSubstituteView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.request.create")]

    class Input(serializers.Serializer):
        substitute_id = serializers.IntegerField(min_value=1)

    def post(self, request, pk):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            row = services.replace_substitute(
                request_id=pk, employee_id=request.principal.user_id,
                substitute_id=data.validated_data["substitute_id"],
                actor_id=request.principal.user_id,
            )
        except services.LeaveError as exc:
            raise ValidationError({"substitute_id": str(exc)}) from exc
        row = LeaveRequest.objects.select_related("leave_type").get(pk=row.pk)
        return Response(_request(row), status=201)


class RequestListView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.request.view", "leave.request.substitute")]

    def get(self, request):
        qs = LeaveRequest.objects.select_related("leave_type")
        if not _may_view_all_records(request.principal):
            related_ids = [
                task.leave_request_id
                for task in LeaveApprovalTask.objects.all().only(
                    "leave_request_id", "assigned_user_id", "authority_role",
                )
                if _role_matches(request.principal, task)
            ]
            qs = qs.filter(pk__in=related_ids)
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in {value for value, _ in LeaveRequest.STATUS}:
                raise ValidationError({"status": "Choose a valid leave request status."})
            qs = qs.filter(status=status_filter)
        year = request.query_params.get("year")
        if year:
            try:
                parsed_year = int(year)
            except ValueError as exc:
                raise ValidationError({"year": "Enter a valid calendar year."}) from exc
            qs = qs.filter(start_date__year=parsed_year)
        rows = list(qs[:250])
        people = directory.get_users([row.employee_id for row in rows])
        tasks = {}
        for task in LeaveApprovalTask.objects.filter(
            leave_request_id__in=[row.pk for row in rows], status="pending",
        ):
            if _role_matches(request.principal, task):
                tasks.setdefault(task.leave_request_id, task)
        results = []
        for row in rows:
            task = tasks.get(row.pk)
            # Only include the caller's assigned queue items, except for completed
            # history that remains visible under the explicit view permission.
            results.append(_request(row, task=task, employee_name=getattr(people.get(row.employee_id), "display_name", "")))
        return Response({"results": results})


class DecisionView(LeaveView):
    def get_permissions(self):
        action = getattr(self.request, "data", {}).get("action")
        code = "leave.request.substitute" if action in {"accept", "decline"} else "leave.request.approve"
        return [HasModuleGrant("leave")(), HasPermission(code)()]

    class Input(serializers.Serializer):
        action = serializers.ChoiceField(choices=("approve", "reject", "recommend", "not_recommend", "verify", "accept", "decline"))
        note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def post(self, request, pk):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        task = LeaveApprovalTask.objects.filter(leave_request_id=pk, status="pending").order_by("assigned_at").first()
        if not task:
            raise NotFound("No actionable task exists for this leave request.")
        if not _role_matches(request.principal, task):
            raise NotFound("No actionable task exists for this leave request.")
        try:
            row = services.respond_to_task(
                task_id=task.pk, actor_id=request.principal.user_id,
                action=data.validated_data["action"], note=data.validated_data["note"],
            )
        except services.LeaveError as exc:
            raise ValidationError({"action": str(exc)}) from exc
        row = LeaveRequest.objects.select_related("leave_type").get(pk=row.pk)
        return Response(_request(row))


class RelatedRequestView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.request.create")]

    class Input(serializers.Serializer):
        kind = serializers.ChoiceField(choices=("cancellation", "extension", "resumption"))
        start_date = serializers.DateField(required=False)
        end_date = serializers.DateField(required=False)
        reason = serializers.CharField(max_length=1000, trim_whitespace=True)
        substitute_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
        actual_return_date = serializers.DateField(required=False)
        document_url = serializers.URLField(max_length=500, required=False, allow_blank=True)

        def validate(self, attrs):
            kind = attrs["kind"]
            if kind == "extension" and (not attrs.get("start_date") or not attrs.get("end_date")):
                raise serializers.ValidationError("Extension requires start_date and end_date.")
            if kind == "resumption" and not attrs.get("actual_return_date"):
                raise serializers.ValidationError({"actual_return_date": "This field is required for resumption."})
            if not attrs.get("reason", "").strip():
                raise serializers.ValidationError({"reason": "Enter a reason for the request."})
            return attrs

    def post(self, request, pk):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            row = services.submit_related_request(
                parent_id=pk, employee_id=request.principal.user_id,
                actor_id=request.principal.user_id, kind=values["kind"],
                start=values.get("start_date", date.min),
                end=values.get("end_date", date.min),
                reason=values["reason"], substitute_id=values.get("substitute_id"),
                actual_return_date=values.get("actual_return_date"),
                document_url=values.get("document_url", ""),
            )
        except services.LeaveError as exc:
            raise ValidationError({"request": str(exc)}) from exc
        return Response(_request(row), status=201)


class TypesView(LeaveView):
    def get_permissions(self):
        base = [HasModuleGrant("leave")()]
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            base.append(HasPermission("leave.type.manage", "leave.request.create")())
        else:
            base.append(HasPermission("leave.type.manage")())
        return base

    def get(self, request, pk=None):
        rows = LeaveType.objects.filter(code__in=("CL", "RH", "SCL", "EL", "COL", "VL"))
        if pk is not None:
            rows = rows.filter(pk=pk)
        if not request.principal.has_permission("leave.type.manage"):
            rows = rows.filter(is_active=True)
        return Response({"results": [{
            "id": row.pk, "code": row.code, "name": row.name,
            "annual_entitlement": str(row.annual_entitlement),
            "carry_forward_limit": str(row.carry_forward_limit),
            "requires_document": row.requires_document, "is_paid": row.is_paid,
            "is_active": row.is_active, "allows_half_day": row.allows_half_day,
            "count_continuously": row.count_continuously, "eligible_kinds": row.eligible_kinds,
        } for row in rows]})

    def post(self, request):
        data = self._validate(request)
        item, created = LeaveType.objects.get_or_create(code=data["code"], defaults=data)
        if not created:
            raise ValidationError({"code": "That ELM leave category already exists."})
        return Response(self._serialize(item), status=201)

    def put(self, request, pk):
        item = LeaveType.objects.filter(pk=pk, code__in=("CL", "RH", "SCL", "EL", "COL", "VL")).first()
        if item is None:
            raise NotFound("ELM leave category not found.")
        data = self._validate(request, partial=True)
        for key, value in data.items():
            setattr(item, key, value)
        item.save(update_fields=[*data, "updated_at"])
        return Response(self._serialize(item))

    def _validate(self, request, partial=False):
        fields = serializers.Serializer(data=request.data, partial=partial)
        fields.fields.update({
            "code": serializers.ChoiceField(choices=("CL", "RH", "SCL", "EL", "COL", "VL"), required=not partial),
            "name": serializers.CharField(max_length=80, required=not partial),
            "annual_entitlement": serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0"), required=not partial),
            "carry_forward_limit": serializers.DecimalField(max_digits=6, decimal_places=2, min_value=Decimal("0"), required=False),
            "requires_document": serializers.BooleanField(required=False),
            "is_paid": serializers.BooleanField(required=False),
            "is_active": serializers.BooleanField(required=False),
            "eligible_kinds": serializers.ListField(
                child=serializers.ChoiceField(choices=("faculty", "staff")), required=False,
            ),
            "count_continuously": serializers.BooleanField(required=False),
            "allows_half_day": serializers.BooleanField(required=False),
        })
        fields.is_valid(raise_exception=True)
        return fields.validated_data

    @staticmethod
    def _serialize(item):
        return {"id": item.pk, "code": item.code, "name": item.name,
                "annual_entitlement": str(item.annual_entitlement),
                "carry_forward_limit": str(item.carry_forward_limit),
                "requires_document": item.requires_document, "is_paid": item.is_paid,
                "is_active": item.is_active, "allows_half_day": item.allows_half_day,
                "count_continuously": item.count_continuously, "eligible_kinds": item.eligible_kinds}


class AdjustBalanceView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.balance.update")]

    class Input(serializers.Serializer):
        employee_id = serializers.IntegerField(min_value=1)
        leave_type_id = serializers.IntegerField(min_value=1)
        year = serializers.IntegerField(min_value=2000, max_value=2100)
        amount = serializers.DecimalField(max_digits=7, decimal_places=2)
        note = serializers.CharField(max_length=500, trim_whitespace=True)

    def post(self, request):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["amount"] == 0 or not values["note"]:
            raise ValidationError("A non-zero adjustment and an audit note are required.")
        leave_type = LeaveType.objects.filter(pk=values["leave_type_id"], code__in=("CL", "RH", "SCL", "EL", "COL", "VL")).first()
        if leave_type is None:
            raise ValidationError({"leave_type_id": "Choose a configured ELM category."})
        with transaction.atomic():
            balance, _ = LeaveBalance.objects.select_for_update().get_or_create(
                employee_id=values["employee_id"], leave_type=leave_type, year=values["year"],
            )
            if balance.available + values["amount"] < 0:
                raise ValidationError({"amount": "Adjustment would make the available balance negative."})
            balance.adjusted += values["amount"]
            balance.save(update_fields=["adjusted", "updated_at"])
            LeaveLedger.objects.create(
                employee_id=balance.employee_id, leave_type=leave_type, year=balance.year,
                amount=values["amount"], kind="adjustment", actor_id=request.principal.user_id,
                note=values["note"],
            )
        return Response({"employee_id": balance.employee_id, "year": balance.year, "available": str(balance.available)})


class LedgerView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.request.view", "leave.request.view_self")]

    def get(self, request):
        raw_id = request.query_params.get("employee_id", request.principal.user_id)
        try:
            employee_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"employee_id": "Enter a valid employee id."}) from exc
        if employee_id != request.principal.user_id and not _may_view_all_records(request.principal):
            raise NotFound("Leave history not found.")
        rows = LeaveLedger.objects.filter(employee_id=employee_id).select_related("leave_type")[:200]
        return Response({"results": [{
            "id": row.pk, "type": row.leave_type.name, "amount": str(row.amount),
            "kind": row.kind, "year": row.year, "note": row.note,
            "created_at": row.created_at.isoformat(),
        } for row in rows]})


class AdminLeaveView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.configuration.manage")]


class OfflineRecordView(LeaveView):
    permission_classes = [HasModuleGrant("leave"), HasPermission("leave.record.offline")]

    class Input(serializers.Serializer):
        employee_id = serializers.IntegerField(min_value=1)
        leave_type_id = serializers.IntegerField(min_value=1)
        start_date = serializers.DateField()
        end_date = serializers.DateField()
        reason = serializers.CharField(max_length=1000, trim_whitespace=True)
        reference = serializers.CharField(max_length=200, trim_whitespace=True)
        evidence_url = serializers.URLField(max_length=500)

    def post(self, request):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            row = services.record_offline_leave(
                employee_id=values["employee_id"], leave_type_id=values["leave_type_id"],
                start=values["start_date"], end=values["end_date"], reason=values["reason"],
                reference=values["reference"], evidence_url=values["evidence_url"],
                actor_id=request.principal.user_id,
            )
        except services.LeaveError as exc:
            raise ValidationError({"record": str(exc)}) from exc
        return Response(_request(row), status=201)


class CalendarView(AdminLeaveView):
    class Input(serializers.Serializer):
        name = serializers.CharField(max_length=120)
        year = serializers.IntegerField(min_value=2000, max_value=2100)

    def get(self, request):
        rows = LeaveCalendar.objects.prefetch_related("dates").order_by("-year", "name")
        return Response({"results": [{
            "id": row.pk, "name": row.name, "year": row.year,
            "status": row.status,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "dates": [{"id": item.pk, "date": item.date.isoformat(), "kind": item.kind, "label": item.label} for item in row.dates.all()],
        } for row in rows]})

    def post(self, request):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        row = LeaveCalendar.objects.create(**data.validated_data)
        return Response({"id": row.pk, "name": row.name, "year": row.year, "status": row.status}, status=201)


class CalendarDatesView(AdminLeaveView):
    class Input(serializers.Serializer):
        date = serializers.DateField()
        kind = serializers.ChoiceField(choices=("holiday", "restricted"))
        label = serializers.CharField(max_length=120, trim_whitespace=True)

    def post(self, request, pk):
        calendar = LeaveCalendar.objects.filter(pk=pk, status="draft").first()
        if calendar is None:
            raise NotFound("Only a draft calendar can be changed.")
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["date"].year != calendar.year:
            raise ValidationError({"date": "Calendar dates must belong to the calendar year."})
        item, _ = LeaveCalendarDate.objects.update_or_create(
            calendar=calendar, date=values["date"], kind=values["kind"], defaults={"label": values["label"]},
        )
        return Response({"id": item.pk, "date": item.date.isoformat(), "kind": item.kind, "label": item.label}, status=201)


class PublishCalendarView(AdminLeaveView):
    def post(self, request, pk):
        with transaction.atomic():
            calendar = LeaveCalendar.objects.select_for_update().filter(pk=pk, status="draft").first()
            if calendar is None:
                raise NotFound("Draft calendar not found.")
            LeaveCalendar.objects.select_for_update().filter(year=calendar.year, status="published").update(status="superseded")
            calendar.status = "published"
            calendar.published_at = timezone.now()
            calendar.save(update_fields=["status", "published_at", "updated_at"])
        return Response({"id": calendar.pk, "year": calendar.year, "status": calendar.status})


class VacationPeriodView(AdminLeaveView):
    class Input(serializers.Serializer):
        start_date = serializers.DateField()
        end_date = serializers.DateField()
        source_reference = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def get(self, request):
        return Response({"results": [{
            "id": row.pk, "start_date": row.start_date.isoformat(),
            "end_date": row.end_date.isoformat(), "source_reference": row.source_reference,
        } for row in LeaveVacationPeriod.objects.all()]})

    def post(self, request):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["end_date"] < values["start_date"]:
            raise ValidationError({"end_date": "End date must be on or after start date."})
        row = LeaveVacationPeriod.objects.create(**values)
        return Response({"id": row.pk, "start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat(), "source_reference": row.source_reference}, status=201)


class AuthorityView(AdminLeaveView):
    class Input(serializers.Serializer):
        unit_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
        category = serializers.ChoiceField(choices=("CL", "RH", "SCL", "EL", "COL", "VL"))
        step_order = serializers.IntegerField(min_value=1, max_value=99)
        authority_role = serializers.CharField(max_length=80)
        assigned_user_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
        is_establishment = serializers.BooleanField(required=False, default=False)
        optional_step = serializers.BooleanField(required=False, default=False)
        is_active = serializers.BooleanField(required=False, default=True)

    def get(self, request):
        return Response({"results": [{
            "id": row.pk, "unit_name": row.unit_name, "category": row.category,
            "step_order": row.step_order, "authority_role": row.authority_role,
            "assigned_user_id": row.assigned_user_id, "is_establishment": row.is_establishment,
            "optional_step": row.optional_step, "is_active": row.is_active,
        } for row in LeaveAuthority.objects.all()]})

    def post(self, request):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        row = LeaveAuthority.objects.create(**data.validated_data)
        return Response({"id": row.pk, "authority_role": row.authority_role}, status=201)


class AuthorityDetailView(AdminLeaveView):
    def put(self, request, pk):
        row = LeaveAuthority.objects.filter(pk=pk).first()
        if row is None:
            raise NotFound("Authority route not found.")
        data = AuthorityView.Input(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        for key, value in data.validated_data.items():
            setattr(row, key, value)
        row.save(update_fields=[*data.validated_data, "updated_at"])
        return Response({"id": row.pk, "authority_role": row.authority_role, "is_active": row.is_active})

    def delete(self, request, pk):
        updated = LeaveAuthority.objects.filter(pk=pk).update(is_active=False)
        if not updated:
            raise NotFound("Authority route not found.")
        return Response(status=204)


class WorkflowConfigView(AdminLeaveView):
    class Input(serializers.Serializer):
        reminder_hours = serializers.IntegerField(min_value=1, max_value=8760)
        escalation_hours = serializers.IntegerField(min_value=1, max_value=8760)
        escalation_authority_role = serializers.CharField(max_length=80, required=False, allow_blank=True)
        establishment_step_enabled = serializers.BooleanField(required=False)

    def get(self, request):
        row = services._config()
        return Response({"reminder_hours": row.reminder_hours, "escalation_hours": row.escalation_hours,
                         "escalation_authority_role": row.escalation_authority_role,
                         "establishment_step_enabled": row.establishment_step_enabled})

    def put(self, request):
        data = self.Input(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        if values["escalation_hours"] <= values["reminder_hours"]:
            raise ValidationError({"escalation_hours": "Escalation must follow the reminder threshold."})
        row = services._config()
        for key, value in values.items():
            setattr(row, key, value)
        row.save(update_fields=[*values, "updated_at"])
        return self.get(request)
