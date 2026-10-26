import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { http } from "../../lib/http";

export interface LeaveRequest {
  id: number; employee_id: number; employee_name: string; leave_type: string; leave_type_code: string;
  leave_type_id: number; start_date: string; end_date: string; days: string;
  reason: string; document_url: string; status: string; reviewer_note: string;
  created_at: string;
  station_leave: boolean; station_leave_details: string; substitute_id: number | null;
  substitute_status: string; workflow_stage: string; unit_head_recommendation: string;
  request_kind: string; task_id: number | null; task_action: string;
  director_self_sanction: boolean;
}
export interface LeaveType {
  id: number; code: string; name: string; annual_entitlement: string;
  carry_forward_limit: string; requires_document: boolean; is_paid: boolean;
  is_active: boolean;
  allows_half_day: boolean; count_continuously: boolean; eligible_kinds: string[];
}
export interface LeaveMine {
  year: number;
  balances: { leave_type: string; leave_type_id: number; opening: string;
    accrued: string; adjusted: string; used: string; available: string }[];
  requests: LeaveRequest[];
}
export interface LeaveCalendar {
  id: number; name: string; year: number; status: string; published_at: string | null;
  dates: { id: number; date: string; kind: "holiday" | "restricted"; label: string }[];
}
export interface LeaveAuthority {
  id: number; unit_name: string; category: string; step_order: number; authority_role: string;
  assigned_user_id: number | null; is_establishment: boolean; optional_step: boolean; is_active: boolean;
}
const key = ["leave"];
const configKey = [...key, "configuration"];
const refresh = (qc: ReturnType<typeof useQueryClient>) => qc.invalidateQueries({ queryKey: key });

export function useLeaveMine() {
  return useQuery({ queryKey: [...key, "mine"], queryFn: async () =>
    (await http.get<LeaveMine>("/leave/mine")).data });
}
export function useLeaveRequests(status = "") {
  return useQuery({ queryKey: [...key, "requests", status], queryFn: async () =>
    (await http.get<{ results: LeaveRequest[] }>("/leave/requests", { params: status ? { status } : {} })).data.results });
}
export function useLeaveTypes() {
  return useQuery({ queryKey: [...key, "types"], queryFn: async () =>
    (await http.get<{ results: LeaveType[] }>("/leave/types")).data.results });
}
export function useCreateLeaveRequest() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: Record<string, unknown>) =>
    (await http.post<LeaveRequest>("/leave/requests/create", body)).data,
    onSuccess: () => refresh(qc) });
}
export function useLeaveAction() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { id: number; action: "approve" | "reject" | "recommend" | "not_recommend" | "verify" | "accept" | "decline"; note?: string }) =>
    (await http.post<LeaveRequest>(`/leave/requests/${body.id}/decision`, body)).data,
    onSuccess: () => refresh(qc) });
}
export function useCancelLeave() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (id: number) =>
    (await http.post(`/leave/requests/${id}/cancel`)).data,
    onSuccess: () => refresh(qc) });
}
export function useReplaceLeaveSubstitute() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { id: number; substitute_id: number }) =>
    (await http.post<LeaveRequest>(`/leave/requests/${body.id}/substitute`, { substitute_id: body.substitute_id })).data,
    onSuccess: () => refresh(qc) });
}
export function useCreateRelatedLeaveRequest() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { id: number; kind: "cancellation" | "extension" | "resumption"; start_date?: string; end_date?: string; actual_return_date?: string; reason: string }) =>
    (await http.post<LeaveRequest>(`/leave/requests/${body.id}/related`, body)).data,
    onSuccess: () => refresh(qc) });
}
export function useSaveLeaveType() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: Partial<LeaveType> & { id?: number }) => {
    const { id, ...values } = body;
    return id
      ? (await http.put<LeaveType>(`/leave/types/${id}`, values)).data
      : (await http.post<LeaveType>("/leave/types", values)).data;
  },
    onSuccess: () => refresh(qc) });
}
export function useAdjustLeaveBalance() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { employee_id: number; leave_type_id: number; year: number; amount: number; note: string }) =>
    (await http.post("/leave/balances/adjust", body)).data,
    onSuccess: () => refresh(qc) });
}

export function useLeaveCalendars() {
  return useQuery({ queryKey: [...configKey, "calendars"], queryFn: async () =>
    (await http.get<{ results: LeaveCalendar[] }>("/leave/calendars")).data.results });
}
export function useCreateLeaveCalendar() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { name: string; year: number }) =>
    (await http.post<LeaveCalendar>("/leave/calendars", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: configKey }) });
}
export function useAddLeaveCalendarDate() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { id: number; date: string; kind: "holiday" | "restricted"; label: string }) =>
    (await http.post(`/leave/calendars/${body.id}/dates`, { date: body.date, kind: body.kind, label: body.label })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: configKey }) });
}
export function usePublishLeaveCalendar() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (id: number) => (await http.post(`/leave/calendars/${id}/publish`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: configKey }) });
}
export function useLeaveVacationPeriods() {
  return useQuery({ queryKey: [...configKey, "vacation-periods"], queryFn: async () =>
    (await http.get<{ results: { id: number; start_date: string; end_date: string; source_reference: string }[] }>("/leave/vacation-periods")).data.results });
}
export function useCreateLeaveVacationPeriod() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { start_date: string; end_date: string; source_reference: string }) =>
    (await http.post("/leave/vacation-periods", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: configKey }) });
}
export function useLeaveAuthorities() {
  return useQuery({ queryKey: [...configKey, "authorities"], queryFn: async () =>
    (await http.get<{ results: LeaveAuthority[] }>("/leave/authorities")).data.results });
}
export function useSaveLeaveAuthority() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: Partial<LeaveAuthority> & { id?: number; category?: string; step_order?: number; authority_role?: string }) => {
    const { id, ...values } = body;
    return id ? (await http.put(`/leave/authorities/${id}`, values)).data
      : (await http.post("/leave/authorities", values)).data;
  }, onSuccess: () => qc.invalidateQueries({ queryKey: configKey }) });
}
export function useLeaveWorkflowConfig() {
  return useQuery({ queryKey: [...configKey, "workflow"], queryFn: async () =>
    (await http.get<{ reminder_hours: number; escalation_hours: number; escalation_authority_role: string; establishment_step_enabled: boolean }>("/leave/workflow-config")).data });
}
export function useSaveLeaveWorkflowConfig() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { reminder_hours: number; escalation_hours: number; escalation_authority_role: string; establishment_step_enabled: boolean }) =>
    (await http.put("/leave/workflow-config", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: configKey }) });
}
export function useRecordOfflineLeave() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: async (body: { employee_id: number; leave_type_id: number; start_date: string; end_date: string; reason: string; reference: string; evidence_url: string }) =>
    (await http.post("/leave/requests/offline", body)).data,
    onSuccess: () => refresh(qc) });
}
