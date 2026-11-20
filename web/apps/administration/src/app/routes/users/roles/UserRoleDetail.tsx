import { findNode, selectUserRoleById, useListUserRolesQuery, useNodeTree } from "@/api";
import { UserRoleRoutes } from "@/app/routes";
import { DetailField, DetailLayout, DetailView } from "@/components";
import { useCurrentNode } from "@/hooks";
import { Edit as EditIcon } from "@mui/icons-material";
import { Alert, Box, Chip } from "@mui/material";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

export const UserRoleDetail: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { root } = useNodeTree();
  const { roleId } = useParams();
  const navigate = useNavigate();
  const { role, hasRoles, error } = useListUserRolesQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ currentData, ...rest }) => ({
        ...rest,
        role: currentData ? selectUserRoleById(currentData, Number(roleId)) : undefined,
        hasRoles: currentData !== undefined,
      }),
    }
  );

  if (error) {
    return <Alert severity="error">{t("common.loadingError")}</Alert>;
  }

  if (role === undefined) {
    return hasRoles ? <Alert severity="warning">{t("userRole.notFound")}</Alert> : <Loading />;
  }

  return (
    <DetailLayout
      title={role.name}
      routes={UserRoleRoutes}
      elementNodeId={role.node_id}
      actions={[
        {
          label: t("edit"),
          onClick: () => navigate(UserRoleRoutes.edit(roleId)),
          color: "primary",
          icon: <EditIcon />,
        },
      ]}
    >
      <DetailView>
        <DetailField
          label={t("common.definedAtNode")}
          value={findNode(role.node_id, root)?.name ?? `#${role.node_id}`}
        />
        <DetailField label={t("userRole.isPrivileged")} value={role.is_privileged ? t("common.yes") : t("common.no")} />
        <DetailField
          label={t("userRole.privileges")}
          value={
            role.privileges.length > 0 ? (
              <Box component="span" sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}>
                {[...role.privileges].sort().map((privilege) => (
                  <Chip key={privilege} component="span" label={privilege} size="small" variant="outlined" />
                ))}
              </Box>
            ) : (
              t("userRole.noPrivileges")
            )
          }
        />
      </DetailView>
    </DetailLayout>
  );
};
