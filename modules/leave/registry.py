MODULE = {"code": "leave", "label": "Employee Leave", "icon": "CalendarCheck", "base_path": "/leave", "nav_section": "People", "sort_order": 20, "status": "active"}

NAV_ITEMS = [
    {"code": "leave.mine", "label": "My Leave", "icon": "CalendarCheck", "to": "/leave/mine", "required_permission": "leave.request.view_self", "sort_order": 10},
    {"code": "leave.tasks", "label": "My Leave Tasks", "icon": "ClipboardText", "to": "/leave/tasks", "required_permission": "leave.request.substitute", "sort_order": 15},
    {"code": "leave.requests", "label": "Leave Requests", "icon": "ClipboardText", "to": "/leave/requests", "required_permission": "leave.request.view", "sort_order": 20},
    {"code": "leave.settings", "label": "Leave Settings", "icon": "Sliders", "to": "/leave/settings", "required_permission": "leave.type.manage", "sort_order": 30},
]

PERMISSIONS = [
    ("leave.request.view_self", "View own leave requests and balance"),
    ("leave.request.create", "Apply for leave"),
    ("leave.request.delete", "Cancel own pending request"),
    ("leave.request.substitute", "Respond to a responsibility coverage request"),
    ("leave.request.view", "View leave requests, within scope"),
    ("leave.request.approve", "Approve or reject a leave request"),
    ("leave.balance.update", "Adjust a leave balance"),
    ("leave.type.manage", "Configure leave types and entitlement rules"),
    ("leave.record.offline", "Record leave already sanctioned offline"),
    ("leave.configuration.manage", "Maintain leave hierarchy, calendar, and SLA configuration"),
]

ROLE_GRANTS = {
    "faculty": ["leave.request.view_self", "leave.request.create", "leave.request.delete", "leave.request.substitute"],
    "staff": ["leave.request.view_self", "leave.request.create", "leave.request.delete", "leave.request.substitute"],
    "Unit Head": ["leave.request.view_self", "leave.request.create", "leave.request.delete", "leave.request.view", "leave.request.approve"],
    "Deputy Registrar (Estt.)": ["leave.request.view", "leave.request.approve"],
    "Dean": ["leave.request.view", "leave.request.approve"],
    "Registrar": ["leave.request.view", "leave.request.approve"],
    "Director": ["leave.request.view", "leave.request.approve"],
    "Leave Administrator": ["leave.request.view", "leave.balance.update", "leave.type.manage", "leave.record.offline", "leave.configuration.manage"],
    "hr_officer": ["leave.request.view_self", "leave.request.create", "leave.request.delete", "leave.request.view", "leave.request.approve", "leave.balance.update", "leave.type.manage", "leave.record.offline", "leave.configuration.manage"],
}
