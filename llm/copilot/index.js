window.addEventListener("chainlit-call-fn", (e) => {
  const { name, args, callback } = e.detail;
  callback("You sent: " + args.msg);
});

// ✅ Update Chainlit URL to match Nginx Routing
window.mountChainlitWidget({
  chainlitServer: "http://3.89.163.209/chat",
});

window.addEventListener("chainlit-call-fn", (e) => {
  const { name, args, callback } = e.detail;
  if (name === "formfill") {
      console.log(name, args);
      dash_clientside.set_props("fieldA", { value: args.fieldA });
      dash_clientside.set_props("fieldB", { value: args.fieldB });
      dash_clientside.set_props("fieldC", { value: args.fieldC });
      callback("You sent: " + args.fieldA + " " + args.fieldB + " " + args.fieldC);
  }
});
