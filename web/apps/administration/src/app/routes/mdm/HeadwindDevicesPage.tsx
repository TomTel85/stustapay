import {
  HeadwindDeviceWithMapping,
  useDeleteHeadwindMappingMutation,
  useListHeadwindDevicesQuery,
  useListHeadwindMappingsQuery,
  useRefreshHeadwindMappingTokenMutation,
  useUpsertHeadwindMappingMutation,
} from "@/api/mdm";
import { MdmRoutes, TerminalRoutes } from "@/app/routes";
import { ListLayout } from "@/components";
import { NodeSeenByUser, selectTerminalAll, useListTerminalsQuery, useNodeTree } from "@/api";
import { Loading } from "@stustapay/components";
import { DataGrid, GridActionsCellItem, GridColDef } from "@stustapay/framework";
import { GridColumnVisibilityModel, GridToolbarColumnsButton, GridToolbarContainer } from "@mui/x-data-grid";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TablePagination,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { LoadingButton } from "@mui/lab";
import {
  ExpandMore as ExpandMoreIcon,
  Link as LinkIcon,
  LinkOff as LinkOffIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
} from "@mui/icons-material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { useCurrentNode, useDebounce } from "@/hooks";
import { useOpenModal } from "@stustapay/modal-provider";
import { Link as RouterLink, Navigate } from "react-router-dom";

type DeviceRow = HeadwindDeviceWithMapping;

const DEFAULT_PAGE_SIZE = 100;

const DeviceToolbar = () => (
  <GridToolbarContainer>
    <GridToolbarColumnsButton />
  </GridToolbarContainer>
);

const resolveDeviceLabel = (device: DeviceRow["device"]): string => {
  return (
    device.description ??
    device.device_number ??
    device.serial ??
    device.imei ??
    device.configuration_name ??
    String(device.id)
  );
};

const buildMappingPayload = (device: DeviceRow["device"], terminalId: number) => ({
  terminal_id: terminalId,
  headwind_device_id: String(device.id),
  headwind_device_number: device.device_number ?? null,
  headwind_device_name: resolveDeviceLabel(device),
  headwind_device_serial: device.serial ?? device.imei ?? null,
  headwind_device_model: device.model ?? device.manufacturer ?? null,
});

export const HeadwindDevicesPage: React.FC = () => {
  const { currentNode } = useCurrentNode();

  if (currentNode.id !== 0) {
    return <Navigate to={MdmRoutes.list(0)} replace />;
  }

  return <RootHeadwindDevicesPage />;
};

const RootHeadwindDevicesPage: React.FC = () => {
  const { t } = useTranslation();
  const { currentNode } = useCurrentNode();
  const { root } = useNodeTree();
  const openModal = useOpenModal();
  const terminalLocations = React.useMemo(() => {
    const locations = new Map<number, { eventId: number | null; event: string; node: string }>();
    const visit = (node: NodeSeenByUser, ancestors: NodeSeenByUser[]) => {
      const path = [...ancestors, node];
      const eventIndex = path.findIndex((ancestor) => ancestor.id === node.event_node_id);
      locations.set(node.id, {
        eventId: node.event_node_id,
        event: eventIndex >= 0 ? path[eventIndex].name : t("mdm.noEvent"),
        node:
          (eventIndex >= 0 ? path.slice(eventIndex + 1) : path).map((ancestor) => ancestor.name).join(" / ") ||
          t("mdm.eventRoot"),
      });
      node.children.forEach((child) => visit(child, path));
    };
    visit(root, []);
    return locations;
  }, [root, t]);
  const getTerminalLocation = (nodeId: number) =>
    terminalLocations.get(nodeId) ?? { eventId: null, event: t("mdm.unknownEvent"), node: `#${nodeId}` };

  const [grouping, setGrouping] = React.useState("none");
  const [columnVisibilityModel, setColumnVisibilityModel] = React.useState<GridColumnVisibilityModel>({});
  const [search, setSearch] = React.useState("");
  const debouncedSearch = useDebounce(search, 400);
  const [pageModel, setPageModel] = React.useState({ page: 0, pageSize: DEFAULT_PAGE_SIZE });

  const {
    data: devices,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useListHeadwindDevicesQuery({
    nodeId: currentNode.id,
    page: pageModel.page,
    pageSize: pageModel.pageSize,
    search: debouncedSearch || undefined,
  });
  const { data: headwindMappings, isLoading: isMappingsLoading } = useListHeadwindMappingsQuery({
    nodeId: currentNode.id,
  });

  const { data: terminalEntities } = useListTerminalsQuery({ nodeId: currentNode.id });
  const terminals = React.useMemo(
    () => (terminalEntities ? selectTerminalAll(terminalEntities) : []),
    [terminalEntities]
  );

  const [upsertMapping, upsertState] = useUpsertHeadwindMappingMutation();
  const [refreshMapping] = useRefreshHeadwindMappingTokenMutation();
  const [deleteMapping] = useDeleteHeadwindMappingMutation();

  const [dialogDevice, setDialogDevice] = React.useState<DeviceRow | null>(null);
  const [dialogTerminalId, setDialogTerminalId] = React.useState<number | "">("");

  const closeDialog = () => {
    setDialogDevice(null);
    setDialogTerminalId("");
  };

  const handleOpenDialog = (row: DeviceRow) => {
    setDialogDevice(row);
    setDialogTerminalId(row.mapping?.terminal_id ?? "");
  };

  const handleSubmitMapping = async () => {
    if (!dialogDevice || dialogTerminalId === "") {
      return;
    }

    try {
      await upsertMapping({
        nodeId: currentNode.id,
        payload: buildMappingPayload(dialogDevice.device, Number(dialogTerminalId)),
      }).unwrap();
      closeDialog();
    } catch {
      // handled via error boundaries / alerts
    }
  };

  const confirmUnmap = (terminalId: number) => {
    openModal({
      type: "confirm",
      title: t("mdm.unmap"),
      content: t("mdm.unmapConfirm"),
      onConfirm: () => {
        deleteMapping({ nodeId: currentNode.id, terminalId }).catch(() => undefined);
        return true;
      },
    });
  };

  const handleRefreshToken = (terminalId: number) => {
    refreshMapping({ nodeId: currentNode.id, terminalId }).catch(() => undefined);
  };

  const rows = devices ?? [];
  const eventGroups = new Map<
    string,
    { label: string; rows: DeviceRow[]; nodes: Map<number, { label: string; rows: DeviceRow[] }> }
  >();
  rows.forEach((row) => {
    const location = row.mapping ? getTerminalLocation(row.mapping.node_id) : null;
    const key = !row.mapping
      ? "unmapped"
      : location?.eventId != null
        ? `event-${location.eventId}`
        : `unknown-${row.mapping.node_id}`;
    let eventGroup = eventGroups.get(key);
    if (!eventGroup) {
      eventGroup = { label: location?.event ?? t("mdm.notMapped"), rows: [], nodes: new Map() };
      eventGroups.set(key, eventGroup);
    }
    eventGroup.rows.push(row);
    const nodeId = row.mapping?.node_id ?? -1;
    let nodeGroup = eventGroup.nodes.get(nodeId);
    if (!nodeGroup) {
      nodeGroup = { label: location?.node ?? t("mdm.notMapped"), rows: [] };
      eventGroup.nodes.set(nodeId, nodeGroup);
    }
    nodeGroup.rows.push(row);
  });
  const availableTerminals = terminals
    .filter((terminal) => {
      const existingMapping = headwindMappings?.find(
        (mapping) =>
          mapping.terminal_id === terminal.id && mapping.headwind_device_id !== String(dialogDevice?.device.id)
      );
      return !existingMapping;
    })
    .map((terminal) => {
      const location = getTerminalLocation(terminal.node_id);
      return {
        ...terminal,
        ...location,
        group: `${location.event} / ${location.node}`,
        label: `${terminal.name} (#${terminal.id}) — ${location.event} / ${location.node}`,
      };
    })
    .sort((a, b) => a.group.localeCompare(b.group) || a.name.localeCompare(b.name) || a.id - b.id);

  const columns = (() => {
    const renderStatusChip = (
      pushedAt: string | null | undefined,
      status: string | null | undefined,
      errorMessage: string | null | undefined,
      neverLabel: string
    ) => {
      if (!pushedAt) {
        return <Chip size="small" label={neverLabel} />;
      }
      const color = status === "success" ? "success" : status === "error" ? "error" : "default";
      const label =
        status === "success"
          ? t("mdm.pushStatusSuccess")
          : status === "error"
            ? t("mdm.pushStatusError")
            : (status ?? "");
      return (
        <Tooltip title={errorMessage ?? ""}>
          <Chip size="small" color={color} label={label} />
        </Tooltip>
      );
    };

    const cols: GridColDef<DeviceRow>[] = [
      {
        field: "device",
        headerName: t("mdm.device"),
        flex: 1,
        renderCell: (params) => (
          <Stack spacing={0.5}>
            <Typography variant="body2" fontWeight={600}>
              {resolveDeviceLabel(params.row.device)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {params.row.device.configuration_name ?? params.row.device.device_number ?? ""}
            </Typography>
          </Stack>
        ),
      },
      {
        field: "model",
        headerName: t("mdm.model"),
        flex: 0.7,
        valueGetter: (value, row) => row.device.model ?? row.device.manufacturer ?? "",
      },
      {
        field: "serial",
        headerName: t("mdm.serial"),
        flex: 0.7,
        valueGetter: (value, row) => row.device.serial ?? row.device.imei ?? "",
      },
      {
        field: "mapping",
        headerName: t("mdm.mappedTerminal"),
        flex: 1,
        renderCell: (params) => {
          if (!params.row.mapping) {
            return <Typography variant="body2">{t("mdm.notMapped")}</Typography>;
          }
          return (
            <Tooltip title={params.row.mapping.terminal_description ?? ""}>
              <Box
                component={RouterLink}
                to={TerminalRoutes.detail(params.row.mapping.terminal_id, params.row.mapping.node_id)}
                sx={{ textDecoration: "none" }}
              >
                {params.row.mapping.terminal_name}
              </Box>
            </Tooltip>
          );
        },
      },
      {
        field: "event",
        headerName: t("mdm.event"),
        minWidth: 160,
        flex: 0.8,
        valueGetter: (value, row) =>
          row.mapping ? getTerminalLocation(row.mapping.node_id).event : t("mdm.notMapped"),
      },
      {
        field: "node",
        headerName: t("mdm.node"),
        minWidth: 200,
        flex: 1,
        valueGetter: (value, row) => (row.mapping ? getTerminalLocation(row.mapping.node_id).node : t("mdm.notMapped")),
        renderCell: (params) => (
          <Tooltip title={params.value ?? ""}>
            <Typography variant="body2" noWrap>
              {params.value}
            </Typography>
          </Tooltip>
        ),
      },
      {
        field: "tokenPushStatus",
        headerName: t("mdm.tokenPushStatus"),
        flex: 0.6,
        renderCell: (params) => {
          const mapping = params.row.mapping;
          if (!mapping || !mapping.last_token_pushed_at) {
            return <Chip size="small" label={t("mdm.neverPushed")} />;
          }
          return renderStatusChip(
            mapping.last_token_pushed_at,
            mapping.last_push_status,
            mapping.last_push_error,
            t("mdm.neverPushed")
          );
        },
      },
      {
        field: "wifiPushStatus",
        headerName: t("mdm.wifiPushStatus"),
        flex: 0.6,
        renderCell: (params) => {
          const mapping = params.row.mapping;
          if (!mapping) {
            return <Typography variant="body2">{t("mdm.notMapped")}</Typography>;
          }
          return renderStatusChip(
            mapping.last_wifi_pushed_at,
            mapping.last_wifi_push_status,
            mapping.last_wifi_push_error,
            t("mdm.wifiNotConfigured")
          );
        },
      },
      {
        field: "actions",
        type: "actions",
        headerName: t("actions"),
        width: 160,
        getActions: (params) => {
          const actions = [];

          // Only show "Map" button if device is NOT mapped
          if (!params.row.mapping) {
            actions.push(
              <GridActionsCellItem
                key="map"
                icon={<LinkIcon />}
                label={t("mdm.map")}
                onClick={() => handleOpenDialog(params.row)}
              />
            );
          }

          // Show Refresh and Unmap buttons only if device IS mapped
          if (params.row.mapping) {
            actions.push(
              <GridActionsCellItem
                key="refresh"
                icon={<RefreshIcon />}
                label={t("mdm.refreshToken")}
                onClick={() => handleRefreshToken(params.row.mapping!.terminal_id)}
              />
            );
            actions.push(
              <GridActionsCellItem
                key="unmap"
                icon={<LinkOffIcon />}
                label={t("mdm.unmap")}
                onClick={() => confirmUnmap(params.row.mapping!.terminal_id)}
                showInMenu
              />
            );
          }
          return actions;
        },
      },
    ];
    return cols;
  })();

  const renderDeviceGrid = (groupRows: DeviceRow[], grouped = false) => (
    <DataGrid
      autoHeight
      showToolbar
      disableColumnSelector={false}
      slots={{ toolbar: DeviceToolbar }}
      columnVisibilityModel={columnVisibilityModel}
      onColumnVisibilityModelChange={setColumnVisibilityModel}
      rows={groupRows}
      columns={columns}
      getRowId={(row) => String(row.device.id)}
      paginationModel={grouped ? undefined : pageModel}
      onPaginationModelChange={grouped ? undefined : setPageModel}
      pageSizeOptions={grouped ? [50, 100] : [50, 100, 200]}
      loading={isFetching}
      disableRowSelectionOnClick
      sx={{ boxShadow: (theme) => theme.shadows[1] }}
    />
  );

  if (isLoading || isMappingsLoading) {
    return <Loading />;
  }

  const headwindDisabled = (error as { status?: number } | undefined)?.status === 400;

  return (
    <ListLayout title={t("mdm.headwindDevices")}>
      <Stack spacing={2}>
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="center">
          <TextField
            size="small"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("common.search")}
            fullWidth
            InputProps={{
              startAdornment: <SearchIcon fontSize="small" sx={{ mr: 1 }} />,
            }}
          />
          <TextField
            select
            size="small"
            label={t("mdm.grouping")}
            value={grouping}
            onChange={(event) => setGrouping(event.target.value)}
            SelectProps={{ native: true }}
            sx={{ minWidth: 240 }}
          >
            <option value="none">{t("mdm.noGrouping")}</option>
            <option value="event">{t("mdm.groupByEvent")}</option>
            <option value="node">{t("mdm.groupByEventAndNode")}</option>
          </TextField>
          <Button startIcon={<RefreshIcon />} onClick={() => refetch()} disabled={isFetching}>
            {t("refresh")}
          </Button>
        </Stack>
        {headwindDisabled ? (
          <Alert severity="info">{t("mdm.headwindDisabled")}</Alert>
        ) : error ? (
          <Alert severity="error">{t("common.loadingError")}</Alert>
        ) : null}

        {grouping === "none" ? (
          renderDeviceGrid(rows)
        ) : (
          <>
            <Typography variant="body2" color="text.secondary">
              {t("mdm.groupingPageHint")}
            </Typography>
            {Array.from(eventGroups.entries())
              .sort((a, b) => a[1].label.localeCompare(b[1].label))
              .map(([key, group]) => (
                <Accordion key={key} defaultExpanded disableGutters>
                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                    <Typography fontWeight={600}>
                      {group.label} ({group.rows.length})
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    {grouping === "event"
                      ? renderDeviceGrid(group.rows, true)
                      : Array.from(group.nodes.entries())
                          .sort((a, b) => a[1].label.localeCompare(b[1].label))
                          .map(([nodeId, node]) => (
                            <Accordion key={nodeId} defaultExpanded disableGutters>
                              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                <Typography>
                                  {node.label} ({node.rows.length})
                                </Typography>
                              </AccordionSummary>
                              <AccordionDetails>{renderDeviceGrid(node.rows, true)}</AccordionDetails>
                            </Accordion>
                          ))}
                  </AccordionDetails>
                </Accordion>
              ))}
            <TablePagination
              component="div"
              count={-1}
              page={pageModel.page}
              rowsPerPage={pageModel.pageSize}
              rowsPerPageOptions={[50, 100, 200]}
              onPageChange={(_, page) => setPageModel((model) => ({ ...model, page }))}
              onRowsPerPageChange={(event) => setPageModel({ page: 0, pageSize: Number(event.target.value) })}
              slotProps={{ actions: { nextButton: { disabled: rows.length < pageModel.pageSize || isFetching } } }}
            />
          </>
        )}
      </Stack>

      <Dialog open={dialogDevice != null} onClose={closeDialog} fullWidth maxWidth="sm">
        <DialogTitle>{t("mdm.mapDevice")}</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <Box>
              <Typography variant="subtitle2" color="text.secondary">
                {t("mdm.device")}
              </Typography>
              <Typography variant="body1">{dialogDevice ? resolveDeviceLabel(dialogDevice.device) : ""}</Typography>
              <Typography variant="body2" color="text.secondary">
                {dialogDevice?.device.configuration_name ?? dialogDevice?.device.device_number ?? ""}
              </Typography>
            </Box>
            <Autocomplete
              options={availableTerminals}
              value={availableTerminals.find((terminal) => terminal.id === dialogTerminalId) ?? null}
              onChange={(_, terminal) => setDialogTerminalId(terminal?.id ?? "")}
              groupBy={(terminal) => terminal.group}
              getOptionLabel={(terminal) => terminal.label}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              noOptionsText={t("mdm.noAvailableTerminals")}
              renderOption={(props, terminal) => (
                <Box component="li" {...props} key={terminal.id}>
                  <Stack>
                    <Typography variant="body2" fontWeight={600}>
                      {terminal.name} (#{terminal.id})
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {terminal.event} / {terminal.node}
                    </Typography>
                  </Stack>
                </Box>
              )}
              renderInput={(params) => (
                <TextField {...params} label={t("mdm.selectTerminal")} helperText={t("mdm.terminalSearchHint")} />
              )}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>{t("cancel")}</Button>
          <LoadingButton
            onClick={handleSubmitMapping}
            variant="contained"
            loading={upsertState.isLoading}
            disabled={dialogTerminalId === "" || availableTerminals.length === 0}
          >
            {t("mdm.map")}
          </LoadingButton>
        </DialogActions>
      </Dialog>
    </ListLayout>
  );
};
