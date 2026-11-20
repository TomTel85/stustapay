import { Node, NodeSeenByUser } from "@/api";
import { findNode, useTreeForCurrentUser } from "@/api/nodes";
import { nodeUrlBaseRegex } from "@/app/routes";
import {
  extendExpandedNodes,
  selectExpandedNodes,
  setExpandedNodes,
  setSelectedNodes,
  useAppDispatch,
  useAppSelector,
} from "@/store";
import {
  ChevronRight as ChevronRightIcon,
  ExpandMore as ExpandMoreIcon,
  Folder as FolderIcon,
  Event as EventIcon,
  EditOff as EditOffIcon,
} from "@mui/icons-material";
import { SimpleTreeView } from "@mui/x-tree-view";
import { alpha } from "@mui/material/styles";
import { Box, Typography } from "@mui/material";
import * as React from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { NavigationTreeItem } from "./NavigationTreeItem";
import { NodeMenu, isMenuEntryValidAtNode, nodeMenuEntryDefinitions } from "./NodeMenu";

const getNavigationTreeItemLabel = (node: Node) => {
  if (node.event) {
    return EventIcon;
  }
  return FolderIcon;
};

export const NavigationTree: React.FC = () => {
  const { t } = useTranslation();
  const tree = useTreeForCurrentUser();
  const location = useLocation();
  const expanded = useAppSelector(selectExpandedNodes);
  const dispatch = useAppDispatch();

  const setExpanded = React.useCallback(
    (v: string[]) => {
      dispatch(setExpandedNodes(v));
    },
    [dispatch]
  );

  const setSelected = React.useCallback(
    (v: string | null) => {
      dispatch(setSelectedNodes(v));
    },
    [dispatch]
  );

  const handleToggle = (event: React.SyntheticEvent | null, itemIds: string[]) => {
    setExpanded(itemIds);
  };

  const match = location.pathname.match(nodeUrlBaseRegex);
  const currentNode = match ? findNode(Number(match[1]), tree) : undefined;
  const workspaceId = currentNode ? `/node/${currentNode.id}` : null;
  const menuIds = currentNode?.computed_forbidden_objects_at_node
    ? nodeMenuEntryDefinitions
        .filter((entry) => isMenuEntryValidAtNode(entry, currentNode))
        .map((entry) => entry.route(currentNode))
    : [];
  const selected = currentNode
    ? ([...menuIds, `/node/${currentNode.id}`]
        .sort((a, b) => b.length - a.length)
        .find((id) => location.pathname === id || location.pathname.startsWith(`${id}/`)) ?? null)
    : null;

  React.useEffect(() => {
    setSelected(selected);
    if (currentNode) {
      dispatch(
        extendExpandedNodes([`/node/${currentNode.id}`, ...currentNode.parent_ids.map((parent) => `/node/${parent}`)])
      );
    }
  }, [currentNode, selected, setSelected, dispatch]);

  const renderTree = (node: NodeSeenByUser) => (
    <NavigationTreeItem
      key={node.id}
      itemId={`/node/${node.id}`}
      to={`/node/${node.id}`}
      labelText={t(node.name)}
      labelIcon={getNavigationTreeItemLabel(node)}
      suffixIcon={node.read_only ? EditOffIcon : undefined}
    >
      {node.children.map((node) => renderTree(node))}
    </NavigationTreeItem>
  );

  return (
    <Box>
      <Typography component="h2" variant="subtitle2" sx={{ px: 2, pt: 2, pb: 1 }}>
        {t("portal.workspaces")}
      </Typography>
      <SimpleTreeView
        aria-label={t("portal.workspaces")}
        slots={{ collapseIcon: ExpandMoreIcon, expandIcon: ChevronRightIcon }}
        multiSelect={false}
        expandedItems={expanded}
        selectedItems={workspaceId}
        onExpandedItemsChange={handleToggle}
        sx={(theme) => ({
          flexGrow: 1,
          overflowX: "auto",
          overflowY: "auto",
          maxHeight: "35vh",
          px: 1,
          pb: 2,
          "& .MuiTreeItem-content": {
            borderRadius: 1,
            minHeight: 42,
            my: 0.25,
            color: "text.secondary",
            "&:hover": { bgcolor: alpha(theme.palette.primary.main, 0.06) },
            "&.Mui-selected, &.Mui-selected:hover, &.Mui-selected.Mui-focused": {
              bgcolor: alpha(theme.palette.primary.main, 0.12),
              color: "primary.main",
              "& .MuiTypography-root": { fontWeight: 700 },
            },
          },
          "& .MuiTreeItem-groupTransition": { ml: 1.5, pl: 1, borderLeft: 1, borderColor: "divider" },
        })}
      >
        {renderTree(tree)}
      </SimpleTreeView>
      {currentNode && (
        <>
          <Typography component="h2" variant="subtitle2" sx={{ px: 2, pt: 1, pb: 1, overflowWrap: "anywhere" }}>
            {t("portal.tasksInWorkspace", { workspace: t(currentNode.name) })}
          </Typography>
          <NodeMenu node={currentNode} />
        </>
      )}
    </Box>
  );
};
