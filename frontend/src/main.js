import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Redirect, Route, Switch } from "wouter";
import App from "./App";
import { getUser } from "./services/api";
import "./styles.css";

function Root() {
  const user = getUser();
  return (
    <Switch>
      <Route path="/">
        <Redirect to={user ? (user.role === "staff" ? "/proctor" : "/exams") : "/login"} />
      </Route>
      <Route><App /></Route>
    </Switch>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
