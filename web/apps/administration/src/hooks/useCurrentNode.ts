import { NodeSeenByUserRead } from "@/api";
import { useNode, useNodeTree } from "@/api/nodes";
import { useParams } from "react-router-dom";

export const useCurrentNode = (): { currentNode: NodeSeenByUserRead } => {
  const { root } = useNodeTree();
  const { nodeId } = useParams();
  const { node } = useNode({ nodeId: nodeId ? Number(nodeId) : 0 });
  return { currentNode: node ?? root };
};
