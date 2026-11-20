import { NodeSeenByUser, ObjectType, Privilege } from "@/api";
import {
  AccountBalance as AccountBalanceIcon,
  Android as AndroidIcon,
  ConfirmationNumber as ConfirmationNumberIcon,
  Leaderboard as LeaderboardIcon,
  Assessment as AssessmentIcon,
  MeetingRoom as MeetingRoomIcon,
  Money as MoneyIcon,
  Nfc as NfcIcon,
  Person as PersonIcon,
  PointOfSale as PointOfSaleIcon,
  Shield as ShieldIcon,
  ShoppingCart as ShoppingCartIcon,
  Payment as PaymentIcon,
  Smartphone as SmartphoneIcon,
} from "@mui/icons-material";
import * as React from "react";
import { List, ListItemButton, ListItemIcon, ListItemText } from "@mui/material";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CustomerRoutes,
  EntryAreaRoutes,
  MdmRoutes,
  PayoutRunRoutes,
  ProductRoutes,
  SumUpTransactionRoutes,
  TerminalRoutes,
  TicketRoutes,
  TillRoutes,
  TseRoutes,
  UserRoutes,
  UserTagRoutes,
} from "@/app/routes";
import {
  PrivilegeRequirement,
  hasAllPrivileges,
  hasAnyPrivilege,
  normalizePrivilegeRequirement,
} from "@/core/privileges";

type NodeMenuItem = {
  route: (node: NodeSeenByUser) => string;
  icon: React.FC;
  label: string;
  requiresEvent?: boolean;
  requiredPrivileges?: Privilege[];
  requiredAnyPrivileges?: Privilege[];
  requiresOneOfObjectType?: ObjectType[];
  additionalRequirements?: (node: NodeSeenByUser) => boolean;
};

const privilegeOf = (privileges: PrivilegeRequirement): Privilege[] => normalizePrivilegeRequirement(privileges);

export const nodeMenuEntryDefinitions: NodeMenuItem[] = [
  {
    route: (node) => `/node/${node.id}/reports`,
    label: "nodes.reports",
    icon: AssessmentIcon,
    additionalRequirements: (node) =>
      (node.event != null || node.event_node_id != null) &&
      (node.privileges_at_node.includes("view_node_stats") || node.privileges_at_node.includes("node_administration")),
  },
  {
    route: (node) => `/node/${node.id}/stats`,
    label: "nodes.statistics",
    icon: LeaderboardIcon,
    additionalRequirements: (node) =>
      (node.event != null || node.event_node_id != null) &&
      (node.privileges_at_node.includes("view_node_stats") || node.privileges_at_node.includes("node_administration")),
  },
  {
    route: (node) => UserRoutes.list(node.id),
    label: "users",
    icon: PersonIcon,
    requiredAnyPrivileges: ["user_management", "node_administration"],
  },
  {
    route: (node) => ProductRoutes.list(node.id),
    label: "products",
    icon: ShoppingCartIcon,
    requiredPrivileges: privilegeOf(ProductRoutes.privilege),
    requiresOneOfObjectType: ["product"],
  },
  {
    route: (node) => TicketRoutes.list(node.id),
    label: "tickets",
    icon: ConfirmationNumberIcon,
    requiredPrivileges: privilegeOf(TicketRoutes.privilege),
    requiresOneOfObjectType: ["ticket"],
  },
  {
    route: (node) => EntryAreaRoutes.list(node.id),
    label: "entry.entry",
    icon: MeetingRoomIcon,
    requiresEvent: true,
    requiredPrivileges: ["entry_management"],
    requiresOneOfObjectType: ["entry_area", "entry_group"],
  },
  {
    route: (node) => TerminalRoutes.list(node.id),
    label: "terminal.terminals",
    icon: SmartphoneIcon,
    requiredPrivileges: privilegeOf(TerminalRoutes.privilege),
    requiresOneOfObjectType: ["terminal"],
  },
  {
    route: (node) => MdmRoutes.list(node.id),
    label: "mdm.headwindDevices",
    icon: AndroidIcon,
    requiredPrivileges: ["node_administration"],
    additionalRequirements: (node) => node.id === 0,
  },
  {
    route: (node) => TillRoutes.list(node.id),
    label: "tills",
    icon: PointOfSaleIcon,
    requiredPrivileges: privilegeOf(TillRoutes.privilege),
    requiresOneOfObjectType: ["till"],
  },
  {
    route: (node) => SumUpTransactionRoutes.list(node.id),
    label: "sumup.sumup",
    icon: PaymentIcon,
    requiresEvent: true,
    requiredPrivileges: ["node_administration"],
    additionalRequirements: (node) =>
      node.event != null && (node.event.sumup_payment_enabled || node.event.sumup_topup_enabled),
  },
  {
    route: (node) => CustomerRoutes.list(node.id),
    label: "customer.customers",
    icon: AccountBalanceIcon,
    requiresEvent: true,
    requiredAnyPrivileges: normalizePrivilegeRequirement(CustomerRoutes.privilege),
  },
  {
    route: (node) => PayoutRunRoutes.list(node.id),
    label: "payoutRun.payoutRuns",
    icon: MoneyIcon,
    requiresEvent: true,
    requiresOneOfObjectType: ["account"],
    requiredAnyPrivileges: normalizePrivilegeRequirement(PayoutRunRoutes.privilege),
  },
  {
    route: (node) => UserTagRoutes.list(node.id),
    label: "userTag.userTags",
    icon: NfcIcon,
    requiresEvent: true,
    requiresOneOfObjectType: ["user_tag"],
    requiredPrivileges: ["node_administration"],
  },
  {
    route: (node) => TseRoutes.list(node.id),
    label: "tse.tses",
    icon: ShieldIcon,
    requiresEvent: true,
    requiredPrivileges: ["node_administration"],
  },
];

export const isMenuEntryValidAtNode = (entry: NodeMenuItem, node: NodeSeenByUser) => {
  const isEvent = node.event != null;

  if (!isEvent && entry.requiresEvent === true) {
    return false;
  }

  if (
    entry.requiresOneOfObjectType != null &&
    entry.requiresOneOfObjectType.length > 0 &&
    entry.requiresOneOfObjectType.every((val) => node.computed_forbidden_objects_at_node.includes(val))
  ) {
    return false;
  }

  if (entry.additionalRequirements != null && !entry.additionalRequirements(node)) {
    return false;
  }

  if (
    entry.requiredPrivileges != null &&
    entry.requiredPrivileges.length > 0 &&
    !hasAllPrivileges(node.privileges_at_node, entry.requiredPrivileges)
  ) {
    return false;
  }

  if (
    entry.requiredAnyPrivileges != null &&
    entry.requiredAnyPrivileges.length > 0 &&
    !hasAnyPrivilege(node.privileges_at_node, entry.requiredAnyPrivileges)
  ) {
    return false;
  }
  return true;
};

export interface NodeMenuProps {
  node: NodeSeenByUser;
}

export const NodeMenu: React.FC<NodeMenuProps> = React.memo(({ node }) => {
  const { pathname } = useLocation();
  const { t } = useTranslation();
  if (node.computed_forbidden_objects_at_node === undefined) {
    return null;
  }

  const renderedItems = [];

  for (const menuDefinition of nodeMenuEntryDefinitions) {
    if (!isMenuEntryValidAtNode(menuDefinition, node)) {
      continue;
    }

    const id = menuDefinition.route(node);

    const active = pathname === id || pathname.startsWith(`${id}/`);

    renderedItems.push(
      <ListItemButton
        key={id}
        component={Link}
        to={id}
        selected={active}
        aria-current={active ? "page" : undefined}
        sx={{ borderRadius: 1, minHeight: 42 }}
      >
        <ListItemIcon sx={{ minWidth: 36 }}>
          <menuDefinition.icon />
        </ListItemIcon>
        <ListItemText primary={t(menuDefinition.label)} />
      </ListItemButton>
    );
  }

  return (
    <List
      component="nav"
      aria-label={t("portal.tasksInWorkspace", { workspace: t(node.name) })}
      disablePadding
      sx={{ px: 1, pb: 2 }}
    >
      {renderedItems}
    </List>
  );
});
