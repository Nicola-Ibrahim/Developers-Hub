package devops.resources

default allow := false
default ownership_denied := false
default target_not_found := false

read_actions := {
	"devops_platform.application.resource_management.list_resources.query.ReadResources",
	"devops_platform.application.resource_management.get_resource.query.ReadResource",
	"devops_platform.application.resource_management.get_operation.query.ReadOperation",
	"devops_platform.application.resource_management.read_activity.query.ReadResourceActivity",
}

target_read_actions := {
	"devops_platform.application.resource_management.get_resource.query.ReadResource",
	"devops_platform.application.resource_management.get_operation.query.ReadOperation",
}

allow if {
	input.action in read_actions
	role_allowed
	"resources:read" in input.subject.scopes
	project_matches
	not input.action in target_read_actions
}

allow if {
	input.action in target_read_actions
	role_allowed
	"resources:read" in input.subject.scopes
	project_matches
	input.resource.exists == true
}

allow if {
	input.action == "devops_platform.application.resource_management.catalog.query.ReadCatalog"
	role_allowed
	"catalog:read" in input.subject.scopes
	project_matches
}

allow if {
	input.action == "devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection"
	role_allowed
	"connections:read" in input.subject.scopes
	project_matches
	input.resource.exists == true
	owner_allowed
}

creation_actions := {
	"devops_platform.application.resource_management.submit_database_request.command.RequestTemporaryDatabase",
}

allow if {
	input.action in creation_actions
	role_allowed
	"resources:write" in input.subject.scopes
	project_matches
}

owned_write_actions := {
	"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
	"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
}

allow if {
	input.action in owned_write_actions
	role_allowed
	"resources:write" in input.subject.scopes
	project_matches
	input.resource.exists == true
	owner_allowed
}

role_allowed if { input.subject.role in {"developer", "admin"} }
project_matches if {
	is_string(input.resource.project_id)
	input.resource.project_id != ""
	input.subject.project_id == input.resource.project_id
}
owner_allowed if { input.resource.owner_id == input.subject.id }
owner_allowed if { input.subject.role == "admin" }

targeted_actions := target_read_actions | {
	"devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection",
	"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
	"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
}

target_not_found if {
	input.action in targeted_actions
	role_allowed
	input.subject.project_id == input.resource.project_id
	input.resource.exists == false
	"resources:read" in input.subject.scopes
}

target_not_found if {
	input.action in {
		"devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection",
		"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
		"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
	}
	role_allowed
	input.subject.project_id == input.resource.project_id
	input.resource.exists == false
	input.action == "devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection"
	"connections:read" in input.subject.scopes
}

target_not_found if {
	input.action in {
		"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
		"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
	}
	role_allowed
	input.subject.project_id == input.resource.project_id
	input.resource.exists == false
	"resources:write" in input.subject.scopes
}

ownership_denied if {
	input.action in {
		"devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection",
		"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
		"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
	}
	role_allowed
	project_matches
	input.resource.exists == true
	input.resource.owner_id != input.subject.id
	input.subject.role != "admin"
	input.action == "devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection"
	"connections:read" in input.subject.scopes
}

ownership_denied if {
	input.action in owned_write_actions
	role_allowed
	project_matches
	input.resource.exists == true
	input.resource.owner_id != input.subject.id
	input.subject.role != "admin"
	"resources:write" in input.subject.scopes
}
