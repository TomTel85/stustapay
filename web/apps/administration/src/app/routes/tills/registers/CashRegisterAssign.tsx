import { selectCashRegisterById, useListCashRegistersAdminQuery } from "@/api";
import { withPrivilegeGuard } from "@/app/layout";
import { CashRegistersRoutes } from "@/app/routes";
import { UserSelect } from "@/components/features";
import { useCurrentNode } from "@/hooks";
import { Alert, Button, LinearProgress, Paper, Typography } from "@mui/material";
import { Loading } from "@stustapay/components";
import { toFormikValidationSchema } from "@stustapay/utils";
import { Form, Formik, FormikHelpers } from "formik";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";

// Define schema for the form values
const AssignRegisterSchema = z.object({
  cashier_id: z.number().int().min(1, { message: "Please select a cashier" }),
});

// Type for form values
type FormValues = z.infer<typeof AssignRegisterSchema>;

// Create the API endpoint for assigning a register
import { api } from "@/api/generated/api";

const enhancedApi = api.injectEndpoints({
  endpoints: (build) => ({
    assignRegister: build.mutation<any, { nodeId: number; assignRegisterPayload: { cashier_id: number; cash_register_id: number } }>({
      query: ({ nodeId, assignRegisterPayload }) => ({
        url: `/till-registers/assign-register`,
        method: "POST",
        body: assignRegisterPayload,
        params: {
          node_id: nodeId,
        },
      }),
      invalidatesTags: ["till-registers"],
    }),
  }),
});

export const { useAssignRegisterMutation } = enhancedApi;

export const CashRegisterAssign: React.FC = withPrivilegeGuard("node_administration", () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { currentNode } = useCurrentNode();
  const { registerId } = useParams();
  const { register, isLoading, error } = useListCashRegistersAdminQuery(
    { nodeId: currentNode.id },
    {
      selectFromResult: ({ data, ...rest }) => ({
        ...rest,
        register: data ? selectCashRegisterById(data, Number(registerId)) : undefined,
      }),
    }
  );
  const [assignRegister] = useAssignRegisterMutation();

  // Set initial values for the form
  const initialValues: FormValues = React.useMemo(() => {
    return {
      cashier_id: -1,
    };
  }, []);

  if (error) {
    return <Navigate to={CashRegistersRoutes.list()} />;
  }

  if (isLoading || !register) {
    return <Loading />;
  }

  // Show an error if the register is already assigned to a cashier
  const isAlreadyAssigned = register.current_cashier_id != null;

  const handleSubmit = (values: FormValues, { setSubmitting }: FormikHelpers<FormValues>) => {
    setSubmitting(true);

    assignRegister({
      nodeId: currentNode.id,
      assignRegisterPayload: { cashier_id: values.cashier_id, cash_register_id: Number(registerId) },
    })
      .unwrap()
      .then(() => {
        setSubmitting(false);
        navigate(CashRegistersRoutes.list());
      })
      .catch((err) => {
        setSubmitting(false);
        console.warn("error in assigning cash register", err);
      });
  };

  return (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        {t("register.assign")}
      </Typography>
      {isAlreadyAssigned ? (
        <Alert severity="warning">
          {t("register.alreadyAssigned")}
        </Alert>
      ) : (
        <Formik
          initialValues={initialValues}
          onSubmit={handleSubmit}
          validationSchema={toFormikValidationSchema(AssignRegisterSchema)}
        >
          {({ values, handleSubmit, isSubmitting, setFieldValue, errors, touched }) => (
            <Form onSubmit={handleSubmit}>
              <UserSelect
                variant="standard"
                label={t("register.assignTargetCashier")}
                value={values.cashier_id}
                onChange={(newVal) => setFieldValue("cashier_id", newVal)}
                // TODO: reenable filter for cashiers
                // filterRole="cashier"
                error={touched.cashier_id && !!errors.cashier_id}
                helperText={(touched.cashier_id && errors.cashier_id) as string}
              />

              {isSubmitting && <LinearProgress />}
              <Button
                type="submit"
                fullWidth
                variant="contained"
                color="primary"
                disabled={isSubmitting}
                sx={{ mt: 1 }}
              >
                {t("submit")}
              </Button>
            </Form>
          )}
        </Formik>
      )}
    </Paper>
  );
}); 