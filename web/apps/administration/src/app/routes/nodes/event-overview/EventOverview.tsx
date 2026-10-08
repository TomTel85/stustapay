import * as React from "react";
import { MoneyOverview } from "../MoneyOverview";
import { OfflineActivity } from "./OfflineActivity";

export const EventOverview: React.FC = () => {
  return <>
    <MoneyOverview />
    <OfflineActivity />
  </>;
};
