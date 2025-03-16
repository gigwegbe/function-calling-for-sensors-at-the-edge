// Improved integration script with CORS handling
window.addEventListener("chainlit-call-fn", (e) => {
  const { name, args, callback } = e.detail;
  
  // Handle general callbacks
  if (!name || name === "default") {
    callback("You sent: " + args.msg);
    return;
  }
  
  // Handle form filling functionality
  if (name === "formfill") {
    console.log("Form data received:", name, args);
    
    // Only try to access dash_clientside if it exists
    if (window.dash_clientside) {
      try {
        dash_clientside.set_props("fieldA", { value: args.fieldA });
        dash_clientside.set_props("fieldB", { value: args.fieldB });
        dash_clientside.set_props("fieldC", { value: args.fieldC });
        callback("Form data processed: " + args.fieldA + " " + args.fieldB + " " + args.fieldC);
      } catch (error) {
        console.error("Error setting form props:", error);
        callback("Error processing form data");
      }
    } else {
      console.warn("dash_clientside is not available");
      callback("Form processing not available");
    }
  }
});

// Determine server URL with proper protocol
const getServerUrl = () => {
  const protocol = window.location.protocol;
  const host = window.location.hostname;
  const port = "8000"; // Your Chainlit server port
  
  if (host === "localhost") {
    return `${protocol}//localhost:${port}`;
  } else {
    return `${protocol}//${host}:${port}`; // Use same protocol as parent
  }
};

// Configure CORS for Chainlit server
const chainlitConfig = {
  chainlitServer: getServerUrl(),
  options: {
    customCss: "body { font-family: 'Roboto', sans-serif; }",
    theme: "dark",
    // Add CORS settings
    fetchOptions: {
      credentials: "include",
      mode: "cors"
    },
    // Disable autofocus in cross-origin iframes
    autofocus: false
  }
};

// Mount the Chainlit widget with improved configuration
try {
  window.mountChainlitWidget(chainlitConfig);
  console.log("Chainlit widget mounted with server:", chainlitConfig.chainlitServer);
} catch (error) {
  console.error("Failed to mount Chainlit widget:", error);
}

// Listen for messages from the iframe (if needed)
try {
  // Use safe postMessage with origin validation
  const targetOrigin = new URL(getServerUrl()).origin;
  iframe.contentWindow.postMessage({ 
      action: "focusInput",
      source: "parent" 
  }, targetOrigin);
  console.log("Focus message sent to iframe");
} catch (error) {
  console.error("Failed to send focusInput message:", error);
}