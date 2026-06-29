document.querySelectorAll('input[type="password"]').forEach((input) => {
    if (input.closest(".password-field")) {
        return;
    }

    const wrapper = document.createElement("span");
    wrapper.className = "password-field";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "password-toggle";
    boton.setAttribute("aria-label", "Mostrar contraseña");
    boton.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5c5 0 8.7 4.4 10 7-1.3 2.6-5 7-10 7s-8.7-4.4-10-7c1.3-2.6 5-7 10-7zm0 2c-3.6 0-6.4 2.8-7.7 5 1.3 2.2 4.1 5 7.7 5s6.4-2.8 7.7-5C18.4 9.8 15.6 7 12 7zm0 2.2a2.8 2.8 0 1 1 0 5.6 2.8 2.8 0 0 1 0-5.6z"/></svg>';

    boton.addEventListener("click", () => {
        const visible = input.type === "text";
        input.type = visible ? "password" : "text";
        boton.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
    });

    wrapper.appendChild(boton);
});
