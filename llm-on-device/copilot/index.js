window.mountChainlitWidget({
    chainlitServer: "http://localhost:8000",
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
