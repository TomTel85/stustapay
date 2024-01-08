import { NodeSeenByUserRead } from "@/api";
import {
  AccountBalance as AccountBalanceIcon,
  AddShoppingCart as AddShoppingCartIcon,
  ConfirmationNumber as ConfirmationNumberIcon,
  HistoryEdu as HistoryEduIcon,
  Nfc as NfcIcon,
  Person as PersonIcon,
  PointOfSale as PointOfSaleIcon,
  Shield as ShieldIcon,
  ShoppingCart as ShoppingCartIcon,
} from "@mui/icons-material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { NavigationTreeItem } from "./NavigationTreeItem";

export interface NodeMenuProps {
  node: NodeSeenByUserRead;
}

export const NodeMenu: React.FC<NodeMenuProps> = ({ node }) => {
  const { t } = useTranslation();

  if (node.computed_forbidden_objects_at_node === undefined) {
    return null;
  }

  const items: React.ReactElement[] = [];

  if (
    !node.computed_forbidden_objects_at_node.includes("user") ||
    !node.computed_forbidden_objects_at_node.includes("user_role")
  ) {
    const id = `/node/${node.id}/users`;
    items.push(<NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("users")} labelIcon={PersonIcon} />);
    const cashierId = `/node/${node.id}/cashiers`;
    items.push(
      <NavigationTreeItem
        key={cashierId}
        nodeId={cashierId}
        to={cashierId}
        labelText={t("cashiers")}
        labelIcon={PersonIcon}
      />
    );
  }

  {
    const id = `/node/${node.id}/user-to-roles`;
    items.push(<NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("userToRoles")} labelIcon={PersonIcon} />);
  }

  if (!node.computed_forbidden_objects_at_node.includes("product")) {
    const id = `/node/${node.id}/products`;
    items.push(
      <NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("products")} labelIcon={ShoppingCartIcon} />
    );
  }
  if (!node.computed_forbidden_objects_at_node.includes("ticket")) {
    const id = `/node/${node.id}/tickets`;
    items.push(
      <NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("tickets")} labelIcon={ConfirmationNumberIcon} />
    );
  }
  if (!node.computed_forbidden_objects_at_node.includes("till")) {
    const id = `/node/${node.id}/tills`;
    items.push(<NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("tills")} labelIcon={PointOfSaleIcon} />);
  }
  if (!node.computed_forbidden_objects_at_node.includes("account")) {
    const id = `/node/${node.id}/accounts`;
    items.push(
      <NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("accounts")} labelIcon={AccountBalanceIcon} />
    );
  }
  if (!node.computed_forbidden_objects_at_node.includes("till")) {
    const id = `/node/${node.id}/orders`;
    items.push(
      <NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("orders")} labelIcon={AddShoppingCartIcon} />
    );
  }
  if (!node.computed_forbidden_objects_at_node.includes("user_tag")) {
    const id = `/node/${node.id}/user-tags`;
    items.push(
      <NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("userTag.userTags")} labelIcon={NfcIcon} />
    );
  }
  if (
    !node.computed_forbidden_objects_at_node.includes("tse") &&
    node.privileges_at_node.includes("node_administration")
  ) {
    const id = `/node/${node.id}/tses`;
    items.push(<NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("tse.tses")} labelIcon={ShieldIcon} />);
  }
  if (
    !node.computed_forbidden_objects_at_node.includes("till") &&
    node.privileges_at_node.includes("node_administration")
  ) {
    const id = `/node/${node.id}/dsfinvk`;
    items.push(<NavigationTreeItem key={id} nodeId={id} to={id} labelText={t("dsfinvk")} labelIcon={HistoryEduIcon} />);
  }

  return <>{items}</>;
};
