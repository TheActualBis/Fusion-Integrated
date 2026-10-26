import { useState } from "react";
import { Alert, Badge, Button, Card, Checkbox, Group, Modal, NumberInput, Select, SimpleGrid, Stack, Table, Text, TextInput, Textarea, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { useAuth } from "../../../auth/AuthProvider";
import { PageHeader } from "../../../ui/components/PageHeader";
import { errorMessage } from "../../../lib/http";
import LeaveAdminSettings from "./LeaveAdminSettings";
import { useAdjustLeaveBalance, useCancelLeave, useCreateLeaveRequest, useCreateRelatedLeaveRequest, useLeaveAction, useLeaveMine, useLeaveRequests, useLeaveTypes, useReplaceLeaveSubstitute, useSaveLeaveType, type LeaveRequest } from "../api";

export default function LeavePage({ mode }: { mode: "mine" | "requests" | "tasks" | "settings" }) {
  const { can } = useAuth();
  const mine = useLeaveMine(); const types = useLeaveTypes();
  const [status, setStatus] = useState(""); const queue = useLeaveRequests(status);
  const [open, setOpen] = useState(false); const [typeId, setTypeId] = useState<string | null>(null);
  const [start, setStart] = useState<Date | null>(null); const [end, setEnd] = useState<Date | null>(null);
  const [reason, setReason] = useState(""); const [doc, setDoc] = useState("");
  const [halfDay, setHalfDay] = useState<string | null>(null);
  const [stationLeave, setStationLeave] = useState(false); const [stationDetails, setStationDetails] = useState("");
  const [substituteId, setSubstituteId] = useState<number | string>("");
  const [note, setNote] = useState(""); const [selected, setSelected] = useState<LeaveRequest | null>(null);
  const [replacement, setReplacement] = useState<LeaveRequest | null>(null); const [replacementId, setReplacementId] = useState<number | string>("");
  const [related, setRelated] = useState<LeaveRequest | null>(null); const [relatedKind, setRelatedKind] = useState<"cancellation" | "extension" | "resumption">("cancellation");
  const [relatedEnd, setRelatedEnd] = useState<Date | null>(null); const [returnDate, setReturnDate] = useState<Date | null>(null); const [relatedReason, setRelatedReason] = useState("");
  const create = useCreateLeaveRequest(); const action = useLeaveAction(); const cancel = useCancelLeave(); const saveType = useSaveLeaveType();
  const replaceSubstitute = useReplaceLeaveSubstitute();
  const createRelated = useCreateRelatedLeaveRequest();
  const adjust = useAdjustLeaveBalance();
  const [typeName, setTypeName] = useState(""); const [typeCode, setTypeCode] = useState(""); const [entitlement, setEntitlement] = useState<number | string>(12);
  const [requiresDoc, setRequiresDoc] = useState(false);
  const [employeeId, setEmployeeId] = useState<number | string>(""); const [adjustTypeId, setAdjustTypeId] = useState<string | null>(null);
  const [adjustment, setAdjustment] = useState<number | string>(0); const [adjustNote, setAdjustNote] = useState("");
  const fail = (e: unknown) => notifications.show({ color: "red", message: errorMessage(e) });
  const exportRequests = () => {
    const rows = mine.data?.requests ?? [];
    const fields: (keyof LeaveRequest)[] = ["id", "leave_type", "start_date", "end_date", "days", "reason", "status", "reviewer_note"];
    const csv = [fields.join(","), ...rows.map((row) => fields.map((field) => `"${String(row[field] ?? "").replaceAll('"', '""')}"`).join(","))].join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "my-leave-requests.csv"; link.click(); URL.revokeObjectURL(url);
  };
  const printRequests = () => {
    const rows = mine.data?.requests ?? [];
    const popup = window.open("", "_blank");
    if (!popup) { notifications.show({ color: "red", message: "Allow pop-ups to print your leave requests." }); return; }
    popup.opener = null;
    const escape = (value: string) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
    const body = rows.map((row) => `<tr><td>${row.id}</td><td>${escape(row.leave_type)}</td><td>${escape(row.start_date)} – ${escape(row.end_date)}</td><td>${escape(row.days)}</td><td>${escape(row.reason)}</td><td>${escape(row.status)}</td></tr>`).join("");
    popup.document.write(`<!doctype html><html><head><title>My leave requests</title><style>body{font:14px Arial,sans-serif;margin:32px}h1{font-size:22px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #999;padding:8px;text-align:left;vertical-align:top}th{background:#eee}@media print{body{margin:12mm}}</style></head><body><h1>My leave requests</h1><table><thead><tr><th>Request</th><th>Leave type</th><th>Dates</th><th>Days</th><th>Reason</th><th>Status</th></tr></thead><tbody>${body}</tbody></table><script>window.onload=()=>window.print()</script></body></html>`);
    popup.document.close();
  };
  const submit = async () => {
    if (!typeId || !start || !end || !reason.trim()) return;
    const localDate = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
    try { await create.mutateAsync({ leave_type_id: Number(typeId), start_date: localDate(start), end_date: localDate(end), reason, document_url: doc, half_day: halfDay ?? "", station_leave: stationLeave, station_leave_details: stationDetails, substitute_id: substituteId ? Number(substituteId) : null }); setOpen(false); setReason(""); setHalfDay(null); setStationLeave(false); setStationDetails(""); setSubstituteId(""); notifications.show({ message: "Leave request submitted" }); } catch (e) { fail(e); }
  };
  const decide = async (row: LeaveRequest, actionName: "approve" | "reject" | "recommend" | "not_recommend" | "verify" | "accept" | "decline") => {
    try { await action.mutateAsync({ id: row.id, action: actionName, note }); setSelected(null); setNote(""); notifications.show({ message: `Request ${actionName}d` }); } catch (e) { fail(e); }
  };
  const save = async () => {
    const current = types.data?.find((t) => t.code === typeCode);
    if (!current) return;
    try { await saveType.mutateAsync({ ...current, name: typeName, annual_entitlement: String(entitlement), requires_document: requiresDoc }); notifications.show({ message: `${current.code} policy updated` }); } catch (e) { fail(e); }
  };
  const adjustBalance = async () => {
    try { await adjust.mutateAsync({ employee_id: Number(employeeId), leave_type_id: Number(adjustTypeId), year: new Date().getFullYear(), amount: Number(adjustment), note: adjustNote }); setAdjustNote(""); setAdjustment(0); notifications.show({ message: "Balance adjustment recorded" }); } catch (e) { fail(e); }
  };
  const replace = async () => {
    if (!replacement || !replacementId) return;
    try { await replaceSubstitute.mutateAsync({ id: replacement.id, substitute_id: Number(replacementId) }); setReplacement(null); setReplacementId(""); notifications.show({ message: "Replacement substitute nominated" }); } catch (e) { fail(e); }
  };
  const startRelated = (row: LeaveRequest, kind: "cancellation" | "extension" | "resumption") => {
    setRelated(row); setRelatedKind(kind); setRelatedReason(""); setReturnDate(null);
    const followingDay = new Date(`${row.end_date}T00:00:00`); followingDay.setDate(followingDay.getDate() + 1); setRelatedEnd(followingDay);
  };
  const submitRelated = async () => {
    if (!related || !relatedReason.trim()) return;
    const localDate = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
    const extensionStart = new Date(`${related.end_date}T00:00:00`); extensionStart.setDate(extensionStart.getDate() + 1);
    try {
      await createRelated.mutateAsync({ id: related.id, kind: relatedKind, reason: relatedReason,
        ...(relatedKind === "extension" && relatedEnd ? { start_date: localDate(extensionStart), end_date: localDate(relatedEnd) } : {}),
        ...(relatedKind === "resumption" && returnDate ? { actual_return_date: localDate(returnDate) } : {}) });
      setRelated(null); notifications.show({ message: `${relatedKind} request submitted` });
    } catch (e) { fail(e); }
  };
  return <Stack>
    <PageHeader title={mode === "mine" ? "My leave" : mode === "requests" ? "Leave requests" : mode === "tasks" ? "My leave tasks" : "Leave settings"} subtitle="Plan leave, track your balance, and manage approvals." action={mode === "mine" ? <Button onClick={() => setOpen(true)}>Apply for leave</Button> : undefined} />
    {mode === "mine" && <>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>{(mine.data?.balances ?? []).map((b) => <Card withBorder key={b.leave_type}><Text c="dimmed" size="sm">{b.leave_type}</Text><Title order={2} mt={6}>{b.available} <Text span size="sm" fw={400}>days available</Text></Title><Text size="xs" c="dimmed" mt="xs">{b.used} used this year</Text></Card>)}</SimpleGrid>
      <Card withBorder><Group justify="space-between" mb="md"><Title order={4}>Your requests</Title><Group><Button variant="light" onClick={exportRequests} disabled={!mine.data?.requests.length}>Export CSV</Button><Button variant="light" onClick={printRequests} disabled={!mine.data?.requests.length}>Print</Button></Group></Group><RequestTable rows={mine.data?.requests ?? []} loading={mine.isLoading} own onCancel={(id) => cancel.mutate(id, { onError: fail })} onReplace={setReplacement} onRelated={startRelated} /></Card>
    </>}
    {mode === "requests" && <Card withBorder><Group justify="space-between" mb="md"><Title order={4}>Approval queue</Title><Select value={status} onChange={(v) => setStatus(v ?? "")} data={[{ value: "", label: "All requests" }, ...["pending", "approved", "rejected", "cancelled"].map((v) => ({ value: v, label: v.charAt(0).toUpperCase() + v.slice(1) }))]} w={170} /></Group><RequestTable rows={queue.data ?? []} loading={queue.isLoading} onReview={setSelected} /></Card>}
    {mode === "tasks" && <Card withBorder><Title order={4} mb="md">Assigned to you</Title><RequestTable rows={queue.data ?? []} loading={queue.isLoading} onReview={setSelected} /></Card>}
    {mode === "settings" && <SimpleGrid cols={{ base: 1, md: 2 }}><Card withBorder><Title order={4} mb="md">Update a leave category</Title><Stack><Select label="Category" data={(types.data ?? []).map((t) => ({ value: t.code, label: `${t.code} ? ${t.name}` }))} value={typeCode || null} onChange={(v) => { const item = types.data?.find((t) => t.code === v); setTypeCode(v ?? ""); setTypeName(item?.name ?? ""); setEntitlement(item ? Number(item.annual_entitlement) : 0); setRequiresDoc(item?.requires_document ?? false); }} /><TextInput label="Name" value={typeName} readOnly /><NumberInput label="Annual entitlement (days)" min={0} value={entitlement} onChange={setEntitlement} /><Select label="Supporting document" data={[{ value: "no", label: "Not required" }, { value: "yes", label: "Required" }]} value={requiresDoc ? "yes" : "no"} onChange={(v) => setRequiresDoc(v === "yes")} /><Button onClick={save} disabled={!typeCode} loading={saveType.isPending}>Save policy</Button></Stack></Card><Card withBorder><Title order={4} mb="md">Configured leave types</Title><Stack>{(types.data ?? []).map((t) => <Group key={t.id} justify="space-between" py="xs" style={{ borderBottom: "1px solid var(--mantine-color-gray-2)" }}><div><Text fw={600}>{t.name}</Text><Text size="xs" c="dimmed">{t.code} · {t.annual_entitlement} days/year</Text></div><Badge color={t.is_active ? "green" : "gray"}>{t.is_active ? "Active" : "Inactive"}</Badge></Group>)}{types.data?.length === 0 && <Text c="dimmed">No leave types configured yet.</Text>}</Stack></Card>{can("leave.balance.update") && <Card withBorder><Title order={4} mb="md">Adjust an employee balance</Title><Stack><TextInput label="Employee ID" inputMode="numeric" value={employeeId} onChange={(e) => setEmployeeId(e.currentTarget.value)} /><Select label="Leave type" data={(types.data ?? []).map((t) => ({ value: String(t.id), label: t.name }))} value={adjustTypeId} onChange={setAdjustTypeId} /><NumberInput label="Days to add or remove" description="Use a negative number to deduct days." value={adjustment} onChange={setAdjustment} /><Textarea label="Audit note" value={adjustNote} onChange={(e) => setAdjustNote(e.currentTarget.value)} /><Button onClick={adjustBalance} disabled={!employeeId || !adjustTypeId || Number(adjustment) === 0 || !adjustNote.trim()} loading={adjust.isPending}>Record adjustment</Button></Stack></Card>}</SimpleGrid>}{mode === "settings" && can("leave.configuration.manage") && <LeaveAdminSettings types={types.data ?? []} allowOffline={can("leave.record.offline")} />}
    <Modal opened={open} onClose={() => setOpen(false)} title="Apply for leave"><Stack><Select label="Leave type" data={(types.data ?? []).filter((t) => t.is_active).map((t) => ({ value: String(t.id), label: t.name }))} value={typeId} onChange={(v) => { setTypeId(v); setHalfDay(null); }} /><Group grow><DateInput label="First day" value={start} onChange={setStart} minDate={new Date()} /><DateInput label="Last day" value={end} onChange={setEnd} minDate={start ?? new Date()} /></Group>{types.data?.find((t) => String(t.id) === typeId)?.allows_half_day && start && end && start.toDateString() === end.toDateString() && <Select label="CL portion" clearable value={halfDay} onChange={setHalfDay} data={[{ value: "first", label: "First half" }, { value: "second", label: "Second half" }]} />}{types.data?.find((t) => String(t.id) === typeId)?.requires_document && <TextInput label="Supporting document URL" value={doc} onChange={(e) => setDoc(e.currentTarget.value)} /> }<Checkbox label="I will be outside Jabalpur (Station Leave)" checked={stationLeave} onChange={(e) => setStationLeave(e.currentTarget.checked)} />{stationLeave && <TextInput label="Station Leave details" value={stationDetails} onChange={(e) => setStationDetails(e.currentTarget.value)} />}<TextInput label="Substitute employee ID (if required)" inputMode="numeric" value={substituteId} onChange={(e) => setSubstituteId(e.currentTarget.value)} /><Textarea label="Purpose / reason" minRows={3} value={reason} onChange={(e) => setReason(e.currentTarget.value)} /><Alert color="blue">The system applies the selected leave category's date-counting and calendar rules. A required substitute must accept before the request moves to approval.</Alert><Button onClick={submit} loading={create.isPending} disabled={!typeId || !start || !end || !reason.trim() || (stationLeave && !stationDetails.trim())}>Submit request</Button></Stack></Modal>
    <Modal opened={Boolean(replacement)} onClose={() => setReplacement(null)} title="Replace declined substitute"><Stack><Text>The request remains pending. Nominate one replacement employee to restart the consent step.</Text><TextInput label="Replacement employee ID" inputMode="numeric" value={replacementId} onChange={(e) => setReplacementId(e.currentTarget.value)} /><Button onClick={replace} disabled={!replacementId} loading={replaceSubstitute.isPending}>Send substitute request</Button></Stack></Modal>
    <Modal opened={Boolean(related)} onClose={() => setRelated(null)} title={`${relatedKind.charAt(0).toUpperCase()}${relatedKind.slice(1)} leave`}><Stack>
      <Select label="Request" value={relatedKind} onChange={(value) => value && setRelatedKind(value as typeof relatedKind)} data={[{ value: "cancellation", label: "Cancel approved leave" }, { value: "extension", label: "Extend ongoing leave" }, { value: "resumption", label: "Report return to duty" }]} />
      {relatedKind === "extension" && <DateInput label="New final day" value={relatedEnd} onChange={setRelatedEnd} minDate={related ? new Date(new Date(`${related.end_date}T00:00:00`).getTime() + 86_400_000) : undefined} />}
      {relatedKind === "resumption" && <DateInput label="Actual return-to-duty date" value={returnDate} onChange={setReturnDate} maxDate={new Date()} />}
      <Textarea label="Reason / details" value={relatedReason} onChange={(e) => setRelatedReason(e.currentTarget.value)} minRows={3} />
      <Button onClick={submitRelated} disabled={!relatedReason.trim() || (relatedKind === "extension" && !relatedEnd) || (relatedKind === "resumption" && !returnDate)} loading={createRelated.isPending}>Submit request</Button>
    </Stack></Modal>
    <Modal opened={Boolean(selected)} onClose={() => setSelected(null)} title="Review leave request"><Stack>{selected && <><Text fw={600}>{selected.employee_name} · {selected.leave_type}</Text><Text>{selected.start_date} to {selected.end_date} · {selected.days} days</Text><Text>{selected.reason}</Text>{selected.station_leave && <Text>Station Leave: {selected.station_leave_details}</Text>}{selected.document_url && <Text component="a" href={selected.document_url} target="_blank" rel="noreferrer">Open supporting document</Text>}<Textarea label="Decision note" value={note} onChange={(e) => setNote(e.currentTarget.value)} placeholder="Required when rejecting" /><Group justify="flex-end"><Button variant="default" onClick={() => setSelected(null)}>Close</Button>{selected.task_action === "unit_head_review" ? <><Button color="red" onClick={() => decide(selected, "not_recommend")} loading={action.isPending}>Not recommended</Button><Button onClick={() => decide(selected, "recommend")} loading={action.isPending}>Recommend</Button></> : selected.task_action === "establishment_review" ? <Button onClick={() => decide(selected, "verify")} loading={action.isPending}>Verify and route</Button> : selected.task_action === "substitute_response" ? <><Button color="red" onClick={() => decide(selected, "decline")} loading={action.isPending}>Decline</Button><Button onClick={() => decide(selected, "accept")} loading={action.isPending}>Accept</Button></> : <><Button color="red" onClick={() => decide(selected, "reject")} disabled={!note.trim()} loading={action.isPending}>Reject</Button><Button onClick={() => decide(selected, "approve")} loading={action.isPending}>Approve</Button></>}</Group></>}</Stack></Modal>
  </Stack>;
}

function RequestTable({ rows, loading, own = false, onReview, onCancel, onReplace, onRelated }: { rows: LeaveRequest[]; loading: boolean; own?: boolean; onReview?: (r: LeaveRequest) => void; onCancel?: (id: number) => void; onReplace?: (r: LeaveRequest) => void; onRelated?: (r: LeaveRequest, kind: "cancellation" | "extension" | "resumption") => void }) {
  if (loading) return <Text c="dimmed">Loading leave requests…</Text>;
  if (!rows.length) return <Text c="dimmed" ta="center" py="xl">No leave requests to show.</Text>;
  return <Table.ScrollContainer minWidth={760}><Table highlightOnHover><Table.Thead><Table.Tr>{!own && <Table.Th>Employee</Table.Th>}<Table.Th>Leave type</Table.Th><Table.Th>Dates</Table.Th><Table.Th>Days</Table.Th><Table.Th>Reason</Table.Th><Table.Th>Status</Table.Th>{(onReview || onCancel || onReplace || onRelated) && <Table.Th>Action</Table.Th>}</Table.Tr></Table.Thead><Table.Tbody>{rows.map((r) => <Table.Tr key={r.id}>{!own && <Table.Td>{r.employee_name || `Employee ${r.employee_id}`}</Table.Td>}<Table.Td>{r.leave_type}</Table.Td><Table.Td>{r.start_date} – {r.end_date}</Table.Td><Table.Td>{r.days}</Table.Td><Table.Td>{r.reason}</Table.Td><Table.Td><Badge color={r.status === "approved" ? "green" : r.status === "rejected" ? "red" : r.status === "pending" || r.status.endsWith("_pending") ? "yellow" : "gray"}>{r.status.replaceAll("_", " ")}</Badge></Table.Td>{(onReview || onCancel || onReplace || onRelated) && <Table.Td>{onReview && r.task_id && <Button size="xs" variant="light" onClick={() => onReview(r)}>Review</Button>}{onCancel && ["pending", "cancellation_pending", "extension_pending", "resumption_pending"].includes(r.status) && <Button size="xs" variant="subtle" color="red" onClick={() => onCancel(r.id)}>Withdraw</Button>}{onReplace && ["pending", "extension_pending"].includes(r.status) && r.substitute_status === "declined" && <Button size="xs" variant="light" onClick={() => onReplace(r)}>Replace substitute</Button>}{onRelated && r.status === "approved" && <Button size="xs" variant="light" onClick={() => onRelated(r, "cancellation")}>Related leave action</Button>}</Table.Td>}</Table.Tr>)}</Table.Tbody></Table></Table.ScrollContainer>;
}
