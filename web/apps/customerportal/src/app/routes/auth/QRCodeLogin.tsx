import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useLoginMutation } from "@/api";
import { toast } from "react-toastify";

export const QRCodeLogin: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [login] = useLoginMutation();

  // Extract the pin from the query params
  const pin = searchParams.get("pin");

  React.useEffect(() => {
    if (!pin) {
      toast.error("Invalid QR code, missing PIN.");
      navigate("/login"); // Redirect to login if there's no pin
      return;
    }

    // Perform the login with the pin
    login({ loginPayload: { pin } })
      .unwrap()
      .then(() => {
        navigate("/"); // Redirect to the home page on success
      })
      .catch((err) => {
        console.error(err);
        toast.error("QR code login failed");
        navigate("/login"); // Redirect to login on failure
      });
  }, [pin, login, navigate]);

  return <div>Logging in with QR code...</div>;
};