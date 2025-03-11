import * as React from "react";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { ErrorPage } from "./ErrorPage";
import { AuthenticatedRoot } from "./routes/AuthenticatedRoot";
import { Login } from "./routes/auth/Login";
import { QRCodeLogin } from "./routes/auth/QRCodeLogin";
import { UnauthenticatedRoot } from "./routes/UnauthenticatedRoot";
import { Index } from "./routes/Index";
import { PayoutInfo } from "./routes/PayoutInfo";
import { TopUp } from "./routes/topup";
import { Faq } from "./routes/Faq";
import { Agb } from "./routes/Agb";
import { PrivacyPolicy } from "./routes/PrivacyPolicy";
import { Bon } from "./routes/Bon";

const router = createBrowserRouter([
  {
    path: "/bon/:orderUUID",
    element: <Bon />,
    errorElement: <ErrorPage />,
  },
  {
    path: "/",
    element: <AuthenticatedRoot />,
    errorElement: <ErrorPage />,
    children: [
      {
        path: "",
        element: <Index />,
      },
      {
        path: "payout-info",
        element: <PayoutInfo />,
      },
      {
        path: "topup",
        element: <TopUp />,
      },
    ],
  },
  {
    element: <UnauthenticatedRoot />,
    errorElement: <ErrorPage />,
    children: [
      {
        path: "/login",
        element: <Login />,
      },
      {
        path: "/login/qr",
        element: <QRCodeLogin />, // This is the new component for QR code login
      },
      {
        path: "/faq",
        element: <Faq />,
      },
      {
        path: "/agb",
        element: <Agb />,
      },
      {
        path: "datenschutz",
        element: <PrivacyPolicy />,
      },
    ],
  },
]);

export const Router: React.FC = () => {
  return <RouterProvider router={router} />;
};
