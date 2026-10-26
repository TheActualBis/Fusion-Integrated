import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Checkbox, Group, NumberInput, Select, SimpleGrid, Stack, Switch, Table, TextInput, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { errorMessage } from "../../../lib/http";
import { useAddLeaveCalendarDate, useCreateLeaveCalendar, useCreateLeaveVacationPeriod, useLeaveAuthorities, useLeaveCalendars, useLeaveVacationPeriods, useLeaveWorkflowConfig, usePublishLeaveCalendar, useRecordOfflineLeave, useSaveLeaveAuthority, useSaveLeaveWorkflowConfig, type LeaveType } from "../api";

const dateText = (date: Date | null) => date
  ? `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
  : "";

export default function LeaveAdminSettings({ types, allowOffline }: { types: LeaveType[]; allowOffline: boolean }) {
  const calendars = useLeaveCalendars(); const addCalendar = useCreateLeaveCalendar();
  const addCalendarDate = useAddLeaveCalendarDate(); const publishCalendar = usePublishLeaveCalendar();
  const vacationPeriods = useLeaveVacationPeriods(); const addVacationPeriod = useCreateLeaveVacationPeriod();
  const authorities = useLeaveAuthorities(); const saveAuthority = useSaveLeaveAuthority();
  const workflow = useLeaveWorkflowConfig(); const saveWorkflow = useSaveLeaveWorkflowConfig();
  const recordOffline = useRecordOfflineLeave();
  const [calendarName, setCalendarName] = useState(""); const [calendarYear, setCalendarYear] = useState<number | string>(new Date().getFullYear());
  const [calendarId, setCalendarId] = useState<string | null>(null); const [calendarDate, setCalendarDate] = useState<Date | null>(null);
  const [calendarKind, setCalendarKind] = useState<"holiday" | "restricted">("holiday"); const [calendarLabel, setCalendarLabel] = useState("");
  const [vacationStart, setVacationStart] = useState<Date | null>(null); const [vacationEnd, setVacationEnd] = useState<Date | null>(null); const [vacationSource, setVacationSource] = useState("");
  const [unit, setUnit] = useState(""); const [category, setCategory] = useState<string | null>(null); const [step, setStep] = useState<number | string>(1);
  const [role, setRole] = useState(""); const [assignee, setAssignee] = useState<number | string>(""); const [isEstablishment, setIsEstablishment] = useState(false); const [optional, setOptional] = useState(false);
  const [reminder, setReminder] = useState<number | string>(24); const [escalation, setEscalation] = useState<number | string>(72); const [escalationRole, setEscalationRole] = useState(""); const [establishmentEnabled, setEstablishmentEnabled] = useState(false);
  const [offlineEmployee, setOfflineEmployee] = useState<number | string>(""); const [offlineType, setOfflineType] = useState<string | null>(null);
  const [offlineStart, setOfflineStart] = useState<Date | null>(null); const [offlineEnd, setOfflineEnd] = useState<Date | null>(null);
  const [offlineReason, setOfflineReason] = useState(""); const [offlineReference, setOfflineReference] = useState(""); const [offlineEvidence, setOfflineEvidence] = useState("");
  useEffect(() => {
    if (!workflow.data) return;
    setReminder(workflow.data.reminder_hours); setEscalation(workflow.data.escalation_hours);
    setEscalationRole(workflow.data.escalation_authority_role);
    setEstablishmentEnabled(workflow.data.establishment_step_enabled);
  }, [workflow.data]);
  const fail = (error: unknown) => notifications.show({ color: "red", message: errorMessage(error) });
  const success = (message: string) => notifications.show({ message });
  const createCalendar = async () => {
    try { const row = await addCalendar.mutateAsync({ name: calendarName.trim(), year: Number(calendarYear) }); setCalendarId(String(row.id)); setCalendarName(""); success("Calendar created as draft"); } catch (e) { fail(e); }
  };
  const addDate = async () => {
    if (!calendarId || !calendarDate) return;
    try { await addCalendarDate.mutateAsync({ id: Number(calendarId), date: dateText(calendarDate), kind: calendarKind, label: calendarLabel.trim() }); setCalendarLabel(""); success("Calendar date saved"); } catch (e) { fail(e); }
  };
  const addVacation = async () => {
    if (!vacationStart || !vacationEnd) return;
    try { await addVacationPeriod.mutateAsync({ start_date: dateText(vacationStart), end_date: dateText(vacationEnd), source_reference: vacationSource.trim() }); setVacationSource(""); success("Vacation period added"); } catch (e) { fail(e); }
  };
  const addAuthority = async () => {
    if (!category || !role.trim()) return;
    try { await saveAuthority.mutateAsync({ unit_name: unit.trim(), category, step_order: Number(step), authority_role: role.trim(), assigned_user_id: assignee ? Number(assignee) : null, is_establishment: isEstablishment, optional_step: optional }); setRole(""); success("Approval authority added"); } catch (e) { fail(e); }
  };
  const saveSla = async () => {
    try { await saveWorkflow.mutateAsync({ reminder_hours: Number(reminder), escalation_hours: Number(escalation), escalation_authority_role: escalationRole.trim(), establishment_step_enabled: establishmentEnabled }); success("Workflow settings saved"); } catch (e) { fail(e); }
  };
  const recordOfflineEntry = async () => {
    if (!offlineType || !offlineStart || !offlineEnd) return;
    try { await recordOffline.mutateAsync({ employee_id: Number(offlineEmployee), leave_type_id: Number(offlineType), start_date: dateText(offlineStart), end_date: dateText(offlineEnd), reason: offlineReason.trim(), reference: offlineReference.trim(), evidence_url: offlineEvidence.trim() }); setOfflineReason(""); setOfflineReference(""); setOfflineEvidence(""); success("Previously sanctioned leave recorded"); } catch (e) { fail(e); }
  };

  return <Stack>
    <Alert color="blue">Administrative actions are checked by the server against your Fusion permissions.</Alert>
    <SimpleGrid cols={{ base: 1, md: 2 }}>
      <Card withBorder><Title order={4} mb="md">Leave calendars</Title><Stack>
        <TextInput label="Calendar name" value={calendarName} onChange={(e) => setCalendarName(e.currentTarget.value)} />
        <NumberInput label="Calendar year" min={2000} max={2100} value={calendarYear} onChange={setCalendarYear} />
        <Button onClick={createCalendar} disabled={!calendarName.trim()} loading={addCalendar.isPending}>Create draft calendar</Button>
        <Select label="Draft to edit" data={(calendars.data ?? []).filter((c) => c.status === "draft").map((c) => ({ value: String(c.id), label: `${c.year} · ${c.name}` }))} value={calendarId} onChange={setCalendarId} />
        {calendarId && <><Group grow><DateInput label="Date" value={calendarDate} onChange={setCalendarDate} /><Select label="Kind" data={[{ value: "holiday", label: "Closed holiday" }, { value: "restricted", label: "Restricted holiday" }]} value={calendarKind} onChange={(v) => v && setCalendarKind(v as "holiday" | "restricted")} /></Group>
          <TextInput label="Label" value={calendarLabel} onChange={(e) => setCalendarLabel(e.currentTarget.value)} />
          <Button onClick={addDate} disabled={!calendarDate || !calendarLabel.trim()} loading={addCalendarDate.isPending}>Add or update date</Button>
          <Button color="green" variant="light" onClick={() => publishCalendar.mutate(Number(calendarId), { onSuccess: () => success("Calendar published"), onError: fail })} loading={publishCalendar.isPending}>Publish calendar</Button></>}
        <Table><Table.Thead><Table.Tr><Table.Th>Year</Table.Th><Table.Th>Calendar</Table.Th><Table.Th>Status</Table.Th><Table.Th>Dates</Table.Th></Table.Tr></Table.Thead><Table.Tbody>{(calendars.data ?? []).map((c) => <Table.Tr key={c.id}><Table.Td>{c.year}</Table.Td><Table.Td>{c.name}</Table.Td><Table.Td><Badge>{c.status}</Badge></Table.Td><Table.Td>{c.dates.length}</Table.Td></Table.Tr>)}</Table.Tbody></Table>
      </Stack></Card>
      <Card withBorder><Title order={4} mb="md">Academic vacation periods</Title><Stack>
        <Group grow><DateInput label="First day" value={vacationStart} onChange={setVacationStart} /><DateInput label="Last day" value={vacationEnd} onChange={setVacationEnd} minDate={vacationStart ?? undefined} /></Group>
        <TextInput label="Academic calendar reference" value={vacationSource} onChange={(e) => setVacationSource(e.currentTarget.value)} />
        <Button onClick={addVacation} disabled={!vacationStart || !vacationEnd} loading={addVacationPeriod.isPending}>Add vacation period</Button>
        <Table><Table.Thead><Table.Tr><Table.Th>Dates</Table.Th><Table.Th>Source</Table.Th></Table.Tr></Table.Thead><Table.Tbody>{(vacationPeriods.data ?? []).map((p) => <Table.Tr key={p.id}><Table.Td>{p.start_date} – {p.end_date}</Table.Td><Table.Td>{p.source_reference || "—"}</Table.Td></Table.Tr>)}</Table.Tbody></Table>
      </Stack></Card>
      <Card withBorder><Title order={4} mb="md">Approval hierarchy</Title><Stack>
        <TextInput label="Unit or department (blank for default)" value={unit} onChange={(e) => setUnit(e.currentTarget.value)} />
        <Group grow><Select label="Leave category" data={types.map((t) => ({ value: t.code, label: t.code }))} value={category} onChange={setCategory} /><NumberInput label="Step order" min={1} max={99} value={step} onChange={setStep} /></Group>
        <TextInput label="Authority role/designation" value={role} onChange={(e) => setRole(e.currentTarget.value)} />
        <TextInput label="Assigned Fusion user ID (optional)" inputMode="numeric" value={assignee} onChange={(e) => setAssignee(e.currentTarget.value)} />
        <Checkbox label="Establishment review step" checked={isEstablishment} onChange={(e) => setIsEstablishment(e.currentTarget.checked)} />
        <Checkbox label="Optional step (controlled by workflow setting)" checked={optional} onChange={(e) => setOptional(e.currentTarget.checked)} />
        <Button onClick={addAuthority} disabled={!category || !role.trim()} loading={saveAuthority.isPending}>Add authority step</Button>
        <Table><Table.Thead><Table.Tr><Table.Th>Unit</Table.Th><Table.Th>Type</Table.Th><Table.Th>Step</Table.Th><Table.Th>Authority</Table.Th><Table.Th>Active</Table.Th></Table.Tr></Table.Thead><Table.Tbody>{(authorities.data ?? []).map((a) => <Table.Tr key={a.id}><Table.Td>{a.unit_name || "Default"}</Table.Td><Table.Td>{a.category}</Table.Td><Table.Td>{a.step_order}</Table.Td><Table.Td>{a.authority_role}{a.assigned_user_id ? ` · ${a.assigned_user_id}` : ""}</Table.Td><Table.Td><Switch checked={a.is_active} aria-label={`Toggle ${a.authority_role}`} onChange={(e) => saveAuthority.mutate({ id: a.id, is_active: e.currentTarget.checked }, { onError: fail })} /></Table.Td></Table.Tr>)}</Table.Tbody></Table>
      </Stack></Card>
      <Card withBorder><Title order={4} mb="md">Workflow service levels</Title><Stack>
        <Group grow><NumberInput label="Reminder after (hours)" min={1} max={8760} value={reminder} onChange={setReminder} /><NumberInput label="Escalate after (hours)" min={1} max={8760} value={escalation} onChange={setEscalation} /></Group>
        <TextInput label="Escalation authority role" value={escalationRole} onChange={(e) => setEscalationRole(e.currentTarget.value)} />
        <Checkbox label="Enable optional Establishment step" checked={establishmentEnabled} onChange={(e) => setEstablishmentEnabled(e.currentTarget.checked)} />
        <Button onClick={saveSla} loading={saveWorkflow.isPending}>Save workflow settings</Button>
      </Stack></Card>
      {allowOffline && <Card withBorder><Title order={4} mb="md">Record previously sanctioned leave</Title><Stack>
        <TextInput label="Employee ID" inputMode="numeric" value={offlineEmployee} onChange={(e) => setOfflineEmployee(e.currentTarget.value)} />
        <Select label="Leave category" data={types.map((t) => ({ value: String(t.id), label: t.name }))} value={offlineType} onChange={setOfflineType} />
        <Group grow><DateInput label="First day" value={offlineStart} onChange={setOfflineStart} /><DateInput label="Last day" value={offlineEnd} onChange={setOfflineEnd} minDate={offlineStart ?? undefined} /></Group>
        <TextInput label="Reason" value={offlineReason} onChange={(e) => setOfflineReason(e.currentTarget.value)} />
        <TextInput label="Sanction reference" value={offlineReference} onChange={(e) => setOfflineReference(e.currentTarget.value)} />
        <TextInput label="Evidence URL" value={offlineEvidence} onChange={(e) => setOfflineEvidence(e.currentTarget.value)} />
        <Button onClick={recordOfflineEntry} disabled={!offlineEmployee || !offlineType || !offlineStart || !offlineEnd || !offlineReason.trim() || !offlineReference.trim() || !offlineEvidence.trim()} loading={recordOffline.isPending}>Record offline sanction</Button>
      </Stack></Card>}
    </SimpleGrid>
  </Stack>;
}
