import { useGetRestrictedEventSettingsQuery } from "@/api";
import { useCurrentNode } from "@/hooks";
import { TabContext, TabList, TabPanel } from "@mui/lab";
import { Alert, AlertTitle, Box, Tab } from "@mui/material";
import { Loading } from "@stustapay/components";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { TabBon } from "./TabBon";
import { TabCustomerPortal } from "./TabCustomerPortal";
import { TabGeneral } from "./TabGeneral";
import { TabMail } from "./TabMail";
import { TabPayout } from "./TabPayout";
import { TabSumUp } from "./TabSumUp";

export const Settings: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = React.useState("general");
  const { currentNode } = useCurrentNode();
  // TODO: remove the following line
  const { data: eventSettings, isLoading, error } = useGetRestrictedEventSettingsQuery({ nodeId: currentNode.id });

  if (isLoading || (!eventSettings && !error)) {
    return <Loading />;
  }

  if (!eventSettings || error) {
    return (
      <Alert severity="error">
        <AlertTitle>Error loading event settings</AlertTitle>
      </Alert>
    );
  }

  return (
    <TabContext value={activeTab}>
      <Box display="grid" gridTemplateColumns="min-content auto">
        <Box sx={{ borderRight: 1, borderColor: "divider" }}>
          <TabList onChange={(_, tab) => setActiveTab(tab)} orientation="vertical">
            <Tab label={t("settings.general.tabLabel")} value="general" />
            <Tab label={t("settings.customerPortal.tabLabel")} value="customerPortal" />
            <Tab label={t("settings.sumup.tabLabel")} value="sumup" />
            <Tab label={t("settings.payout.tabLabel")} value="payout" />
            <Tab label={t("settings.bon.tabLabel")} value="bon" />
            <Tab label={t("settings.email.tabLabel")} value="email" />
          </TabList>
        </Box>
        <TabPanel value="general">
          <TabGeneral nodeId={currentNode.id} eventSettings={eventSettings} />
        </TabPanel>
        <TabPanel value="customerPortal">
          <TabCustomerPortal nodeId={currentNode.id} eventSettings={eventSettings} />
        </TabPanel>
        <TabPanel value="sumup">
          <TabSumUp nodeId={currentNode.id} eventSettings={eventSettings} />
        </TabPanel>
        <TabPanel value="payout">
          <TabPayout nodeId={currentNode.id} eventSettings={eventSettings} />
        </TabPanel>
        <TabPanel value="bon">
          <TabBon nodeId={currentNode.id} eventSettings={eventSettings} />
        </TabPanel>
        <TabPanel value="email">
          <TabMail />
        </TabPanel>
      </Box>
    </TabContext>
  );
};
