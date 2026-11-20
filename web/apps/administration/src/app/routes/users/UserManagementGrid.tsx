import { Search } from "@mui/icons-material";
import { Box } from "@mui/material";
import { GridValidRowModel, QuickFilter, QuickFilterControl } from "@mui/x-data-grid";
import { deDE } from "@mui/x-data-grid/locales";
import { DataGrid, DataGridProps } from "@stustapay/framework";
import { useTranslation } from "react-i18next";

const SearchToolbar = () => {
  const { t } = useTranslation();
  const searchLabel = t("common.search");

  return (
    <Box
      sx={{
        p: 1.5,
        width: "100%",
        maxWidth: 320,
        "& input::placeholder": { color: "text.secondary", opacity: 1 },
      }}
    >
      <QuickFilter expanded>
        <QuickFilterControl
          fullWidth
          size="small"
          type="search"
          placeholder={searchLabel}
          slotProps={{
            htmlInput: { "aria-label": searchLabel },
            input: { startAdornment: <Search fontSize="small" sx={{ mr: 1, color: "text.secondary" }} /> },
          }}
        />
      </QuickFilter>
    </Box>
  );
};

export const UserManagementGrid = <Row extends GridValidRowModel>(props: DataGridProps<Row>) => {
  const { i18n } = useTranslation();

  return (
    <DataGrid
      autoHeight
      showToolbar
      getRowHeight={() => "auto"}
      disableRowSelectionOnClick
      slots={{ toolbar: SearchToolbar }}
      localeText={i18n.resolvedLanguage === "de" ? deDE.components.MuiDataGrid.defaultProps.localeText : undefined}
      sx={{ "& .MuiDataGrid-cell": { py: 1, lineHeight: 1.45, overflowWrap: "anywhere" } }}
      {...props}
    />
  );
};
