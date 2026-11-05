import { findNode, useListUserRolesQuery, useListUserToRoleQuery, useNodeTree } from "@/api";
import { useCurrentNode } from "@/hooks";
import * as React from "react";
import { useTranslation } from "react-i18next";

export type RoleAssignment = {
  roleId: number;
  roleName: string;
  nodeId: number;
  nodeName: string;
  inherited: boolean;
};

export const useUserRoleAssignments = (): {
  byUser: Map<number, RoleAssignment[]>;
  isLoading: boolean;
  error: unknown;
} => {
  const { currentNode } = useCurrentNode();
  const { root } = useNodeTree();
  const assignments = useListUserToRoleQuery({ nodeId: currentNode.id });
  const roles = useListUserRolesQuery({ nodeId: currentNode.id });

  const byUser = React.useMemo(() => {
    const grouped = new Map<number, RoleAssignment[]>();
    const roleEntities = roles.currentData?.entities;

    for (const assignment of assignments.currentData ?? []) {
      const userRoles = grouped.get(assignment.user_id) ?? [];
      const node = findNode(assignment.node_id, root);
      for (const roleId of assignment.role_ids) {
        userRoles.push({
          roleId,
          roleName: roleEntities?.[roleId]?.name ?? `#${roleId}`,
          nodeId: assignment.node_id,
          nodeName: node?.name ?? `#${assignment.node_id}`,
          inherited: assignment.node_id !== currentNode.id,
        });
      }
      grouped.set(assignment.user_id, userRoles);
    }

    return grouped;
  }, [assignments.currentData, currentNode.id, roles.currentData, root]);

  return {
    byUser,
    isLoading: assignments.currentData === undefined || roles.currentData === undefined,
    error: assignments.error ?? roles.error,
  };
};

export const RoleAssignmentSummary: React.FC<{ assignments: RoleAssignment[] }> = ({ assignments }) => {
  const { t } = useTranslation();
  if (assignments.length === 0) {
    return <>{t("userToRole.noRoles")}</>;
  }

  return (
    <>
      {assignments.map((assignment, index) => (
        <React.Fragment key={`${assignment.nodeId}-${assignment.roleId}-${index}`}>
          {index > 0 ? "; " : ""}
          {assignment.inherited
            ? t("userToRole.inheritedFrom", { role: assignment.roleName, node: assignment.nodeName })
            : assignment.roleName}
        </React.Fragment>
      ))}
    </>
  );
};
