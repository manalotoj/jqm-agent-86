import { 
  AuthenticatedTemplate, 
  UnauthenticatedTemplate, 
  useMsal 
} from "@azure/msal-react";
import SessionList from "./components/SessionList";

export default function App() {
  const { instance, accounts } = useMsal();
  const activeAccount = accounts[0];

  const handleLogin = () => {
    instance.loginRedirect({
      scopes: ["User.Read"],
    }).catch((error) => console.error("Login failed:", error));
  };

  const handleLogout = () => {
    instance.logoutRedirect().catch((error) => console.error("Logout failed:", error));
  };

  return (
    <div style={{ padding: "20px", fontFamily: "sans-serif" }}>
      <h1>agent-86</h1>

      <UnauthenticatedTemplate>
        <p>You are currently signed out.</p>
        <button onClick={handleLogin} style={{ padding: "10px 20px", cursor: "pointer" }}>
          Sign In
        </button>
      </UnauthenticatedTemplate>

      <AuthenticatedTemplate>
        <p style={{ color: "green", fontWeight: "bold" }}>✔ Successfully Authenticated</p>

        <div style={{ margin: "20px 0", background: "#f0f0f0", padding: "15px", borderRadius: "5px" }}>
          <h3>Account Claims:</h3>
          <ul>
            <li><strong>Name:</strong> {activeAccount?.name || "N/A"}</li>
            <li><strong>Object ID (oid):</strong> {activeAccount?.idTokenClaims?.oid || "N/A"}</li>
          </ul>
        </div>

        <button onClick={handleLogout} style={{ padding: "10px 20px", cursor: "pointer", backgroundColor: "#ff4d4d", color: "#fff", border: "none" }}>
          Sign Out
        </button>

        <hr style={{ margin: "24px 0" }} />

        <SessionList />
      </AuthenticatedTemplate>
    </div>
  );
}