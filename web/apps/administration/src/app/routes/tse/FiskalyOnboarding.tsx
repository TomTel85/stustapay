import {
  Alert,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useListTsesQuery } from "@/api";
import { useCurrentNode, useCurrentUserHasPrivilege, useCurrentUserHasPrivilegeAtNode } from "@/hooks";
import { NodeSeenByUser, useNodeTree } from "@/api";
import {
  CreateFiskalySite,
  FiskalyProvisioningJob,
  useCreateFiskalySiteMutation,
  useGetFiskalySiteStatusQuery,
  useListFiskalySitesQuery,
  useRetryFiskalyProvisioningMutation,
  useStartFiskalyProvisioningMutation,
} from "@/api/fiskaly";

const emptySite = (node: NodeSeenByUser): CreateFiskalySite => ({
  customer_node_id: 0,
  name: node.name,
  operator_name: node.event?.bon_issuer ?? "",
  address_line1: node.event?.bon_address ?? "",
  zip: "",
  town: "",
  country_code: "DEU",
  vat_id: node.event?.ust_id || undefined,
});

const jobIsActive = (job: FiskalyProvisioningJob) => job.status === "queued" || job.status === "running";

export const FiskalyOnboarding: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const canView = useCurrentUserHasPrivilege("node_administration");
  const canAdministerAtNode = useCurrentUserHasPrivilegeAtNode("node_administration");
  const { root } = useNodeTree();
  const canAdminister = canAdministerAtNode(0);
  const { refetch: refetchTses } = useListTsesQuery({ nodeId: currentNode.id });
  const { data: sites = [], isLoading, error, refetch } = useListFiskalySitesQuery({ nodeId: currentNode.id });
  const [selectedSiteId, setSelectedSiteId] = React.useState<number | "">("");
  const [addingSite, setAddingSite] = React.useState(false);
  const [actionError, setActionError] = React.useState(false);
  const [site, setSite] = React.useState<CreateFiskalySite>(() => emptySite(currentNode));
  const [createSite, createSiteState] = useCreateFiskalySiteMutation();
  const [startProvisioning, startState] = useStartFiskalyProvisioningMutation();
  const [retryProvisioning, retryState] = useRetryFiskalyProvisioningMutation();
  const refreshedReadyJobs = React.useRef(new Set<number>());
  const selectedSite = sites.find((candidate) => candidate.id === selectedSiteId);
  const eventNodeId = currentNode.event_node_id ?? (currentNode.event != null ? currentNode.id : null);
  const customerNodes: NodeSeenByUser[] = [];
  const collectCustomerNodes = (node: NodeSeenByUser) => {
    if (node.id !== 0 && node.event_node_id == null) customerNodes.push(node);
    node.children.forEach(collectCustomerNodes);
  };
  collectCustomerNodes(root);
  const { data: jobs = [], refetch: refetchJobs, error: jobsError } = useGetFiskalySiteStatusQuery(
    { nodeId: currentNode.id, siteId: selectedSiteId as number },
    { skip: selectedSiteId === "", pollingInterval: 5000 }
  );

  React.useEffect(() => {
    const readyJobs = jobs.filter((job) => job.status === "ready" && job.tse_id != null);
    const newReadyJobs = readyJobs.filter((job) => !refreshedReadyJobs.current.has(job.id));
    if (newReadyJobs.length > 0) {
      newReadyJobs.forEach((job) => refreshedReadyJobs.current.add(job.id));
      void refetchTses();
    }
  }, [jobs, refetchTses]);

  React.useEffect(() => {
    setSelectedSiteId("");
    setAddingSite(false);
    setActionError(false);
    setSite(emptySite(currentNode));
    refreshedReadyJobs.current.clear();
  }, [currentNode]);

  const handleCreateSite = async () => {
    setActionError(false);
    try {
      const created = await createSite({ nodeId: currentNode.id, newFiskalySite: site }).unwrap();
      setSelectedSiteId(created.id);
      setAddingSite(false);
      await refetch();
    } catch {
      setActionError(true);
    }
  };

  const handleStart = async () => {
    if (!selectedSite || eventNodeId == null) return;
    setActionError(false);
    try {
      await startProvisioning({
        nodeId: currentNode.id,
        newFiskalyProvisioningJob: { site_id: selectedSite.id, event_node_id: eventNodeId, environment: "TEST" },
      }).unwrap();
      await refetchJobs();
    } catch {
      setActionError(true);
    }
  };

  const handleRetry = async (jobId: number) => {
    setActionError(false);
    try {
      await retryProvisioning({ nodeId: currentNode.id, jobId }).unwrap();
      await refetchJobs();
    } catch {
      setActionError(true);
    }
  };

  const changeField = (field: "name" | "operator_name" | "address_line1" | "zip" | "town" | "vat_id") =>
    (event: React.ChangeEvent<HTMLInputElement>) => {
    setSite((current) => ({ ...current, [field]: event.target.value }));
  };

  const translateStep = (step: string) => {
    const key = `tse.fiskalyOnboarding.step.${step}`;
    const translated = t(key);
    return translated === key ? step : translated;
  };

  const busy = createSiteState.isLoading || startState.isLoading || retryState.isLoading;
  const showActions = canAdminister;

  return (
    <Paper sx={{ p: { xs: 2, sm: 3 }, mb: 3 }}>
      <Stack spacing={2}>
        <div>
          <Typography variant="h6">{t("tse.fiskalyOnboarding.title")}</Typography>
          <Typography variant="body2" color="text.secondary">
            {t("tse.fiskalyOnboarding.description")}
          </Typography>
        </div>

        {error && <Alert severity="error">{t("tse.fiskalyOnboarding.loadError")}</Alert>}
        {actionError && <Alert severity="error">{t("tse.fiskalyOnboarding.actionError")}</Alert>}
        {isLoading ? (
          <Typography>{t("tse.fiskalyOnboarding.loading")}</Typography>
        ) : (
          <FormControl fullWidth>
            <InputLabel id="fiskaly-site-label">{t("tse.fiskalyOnboarding.site")}</InputLabel>
            <Select<number | "">
              labelId="fiskaly-site-label"
              label={t("tse.fiskalyOnboarding.site")}
              value={selectedSiteId}
              onChange={(event) => setSelectedSiteId(event.target.value === "" ? "" : Number(event.target.value))}
            >
              {sites.map((entry) => (
                <MenuItem key={entry.id} value={entry.id}>
                  {entry.name} — {entry.operator_name} ({entry.town})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        )}

        {!canView && <Alert severity="info">{t("tse.fiskalyOnboarding.noAccess")}</Alert>}
        {showActions && (
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <Button variant="outlined" onClick={() => setAddingSite((open) => !open)}>
              {addingSite ? t("cancel") : t("tse.fiskalyOnboarding.addSite")}
            </Button>
            <Button variant="contained" disabled={!selectedSite || eventNodeId == null || busy} onClick={() => void handleStart()}>
              {t("tse.fiskalyOnboarding.startTest")}
            </Button>
          </Stack>
        )}

        {addingSite && showActions && (
          <Stack spacing={1.5}>
            <Typography variant="subtitle1">{t("tse.fiskalyOnboarding.newSite")}</Typography>
            <FormControl fullWidth required>
              <InputLabel id="fiskaly-customer-node-label">{t("tse.fiskalyOnboarding.customer")}</InputLabel>
              <Select
                labelId="fiskaly-customer-node-label"
                label={t("tse.fiskalyOnboarding.customer")}
                value={site.customer_node_id || ""}
                onChange={(event) => setSite((current) => ({ ...current, customer_node_id: Number(event.target.value) }))}
              >
                {customerNodes.map((node) => (
                  <MenuItem key={node.id} value={node.id}>{node.name}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField required label={t("tse.fiskalyOnboarding.siteName")} value={site.name} onChange={changeField("name")} />
            <TextField required label={t("tse.fiskalyOnboarding.operator")} value={site.operator_name} onChange={changeField("operator_name")} />
            <TextField required label={t("tse.fiskalyOnboarding.address")} value={site.address_line1} onChange={changeField("address_line1")} />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
              <TextField required label={t("tse.fiskalyOnboarding.zip")} value={site.zip} onChange={changeField("zip")} />
              <TextField required label={t("tse.fiskalyOnboarding.town")} value={site.town} onChange={changeField("town")} />
              <TextField required label={t("tse.fiskalyOnboarding.countryCode")} value={site.country_code ?? "DEU"} disabled />
            </Stack>
            <TextField label={t("tse.fiskalyOnboarding.vatId")} value={site.vat_id ?? ""} onChange={changeField("vat_id")} />
            <Button
              variant="contained"
              disabled={busy || !site.customer_node_id || !site.name.trim() || !site.operator_name.trim() || !site.address_line1.trim() || !site.zip.trim() || !site.town.trim()}
              onClick={() => void handleCreateSite()}
            >
              {t("tse.fiskalyOnboarding.saveSite")}
            </Button>
          </Stack>
        )}

        {canView && jobs.length > 0 && (
          <Stack spacing={1}>
            <Typography variant="subtitle1">{t("tse.fiskalyOnboarding.jobs")}</Typography>
            {jobs.map((job) => (
              <Paper key={job.id} variant="outlined" sx={{ p: 1.5 }}>
                <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} spacing={1}>
                  <Typography sx={{ flex: 1 }}>
                    {job.environment} · {t(`tse.fiskalyOnboarding.status.${job.status}`)} · {translateStep(job.step)}
                  </Typography>
                  {job.last_error && <Alert severity="error" sx={{ py: 0 }}>{job.last_error}</Alert>}
                  {showActions && !jobIsActive(job) && job.status !== "ready" && job.environment === "TEST" && (
                    <Button disabled={busy} onClick={() => void handleRetry(job.id)}>
                      {t("tse.fiskalyOnboarding.retry")}
                    </Button>
                  )}
                </Stack>
              </Paper>
            ))}
          </Stack>
        )}
        {jobsError && <Alert severity="error">{t("tse.fiskalyOnboarding.statusError")}</Alert>}
      </Stack>
    </Paper>
  );
};
