import * as React from "react";
import { Typography } from "@mui/material";
import { useCurrentNode } from "@/hooks";
import { OfflineActivity } from "./OfflineActivity";

export const EventOverview: React.FC = () => {
  const { currentNode } = useCurrentNode();

  return (
    <>
      <Typography component="h1" variant="h4" sx={{ overflowWrap: "anywhere" }}>
        {currentNode.name}
      </Typography>
      <OfflineActivity />
    </>
  );
};
