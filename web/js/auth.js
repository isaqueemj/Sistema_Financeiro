// Caminho: web/js/auth.js

let estadoAtual = "login";
let identificadorPendente2FA = "";
let tokenResetUrl = null;

document.addEventListener("DOMContentLoaded", () => {
    configurarBotoesOlhoSenha();
    configurarAlternanciaSplitScreen();
    configurarInputsOTP2FA();
    configurarFormularioLogin();
    configurarFormulario2FA();
    configurarFormularioCadastro();
    configurarFormularioEsqueciSenha();
    configurarFormularioRedefinirSenha();

    // Verifica se o usuário abriu o link de redefinição de senha vindo do e-mail (?reset_token=...)
    const params = new URLSearchParams(window.location.search);
    if (params.has("reset_token")) {
        tokenResetUrl = params.get("reset_token");
        mostrarVisao("reset-password");
    }
});

function configurarBotoesOlhoSenha() {
    document.querySelectorAll(".btn-toggle-password").forEach((botao) => {
        botao.addEventListener("click", () => {
            const targetId = botao.getAttribute("data-target");
            const inputSenha = document.getElementById(targetId);
            const icone = botao.querySelector("i");
            if (!inputSenha) return;

            if (inputSenha.type === "password") {
                inputSenha.type = "text";
                icone.classList.replace("bi-eye", "bi-eye-slash");
            } else {
                inputSenha.type = "password";
                icone.classList.replace("bi-eye-slash", "bi-eye");
            }
        });
    });
}

function configurarAlternanciaSplitScreen() {
    const btnAlternar = document.getElementById("btn-alternar-modo");
    const btnVoltarLogin = document.getElementById("btn-voltar-login");

    if (btnAlternar) {
        btnAlternar.addEventListener("click", () => {
            if (estadoAtual === "login" || estadoAtual === "2fa" || estadoAtual === "reset-password") {
                mostrarVisao("register");
            } else {
                mostrarVisao("login");
            }
        });
    }

    if (btnVoltarLogin) {
        btnVoltarLogin.addEventListener("click", () => mostrarVisao("login"));
    }
}

function mostrarVisao(novaVisao) {
    estadoAtual = novaVisao;
    ocultarAlerta("auth-alert");

    const views = {
        "login": document.getElementById("view-login"),
        "2fa": document.getElementById("view-2fa"),
        "register": document.getElementById("view-register"),
        "reset-password": document.getElementById("view-reset-password")
    };

    Object.values(views).forEach((v) => v && v.classList.remove("active"));
    if (views[novaVisao]) views[novaVisao].classList.add("active");

    const ctaTitulo = document.getElementById("cta-titulo");
    const ctaDescricao = document.getElementById("cta-descricao");
    const btnAlternar = document.getElementById("btn-alternar-modo");

    if (novaVisao === "register") {
        ctaTitulo.textContent = "Já possui conta?";
        ctaDescricao.textContent = "Acesse agora usando seu e-mail ou seu @Telegram vinculado.";
        btnAlternar.textContent = "FAZER LOGIN";
    } else {
        ctaTitulo.textContent = "Novo por aqui?";
        ctaDescricao.textContent = "Cadastre-se vinculando seu @Telegram obrigatório e registre gastos por linguagem natural com gráficos em tempo real.";
        btnAlternar.textContent = "CRIAR CONTA";
    }

    if (novaVisao === "2fa") {
        const primeiroInput = document.querySelector(".otp-input");
        if (primeiroInput) primeiroInput.focus();
    }
}

function validarIdentificadorHibrido(valor) {
    const limpo = valor.trim();
    const regexEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const regexTelegram = /^@[a-zA-Z0-9_]{3,32}$/;

    if (regexEmail.test(limpo)) {
        return { valido: true, tipo: "email", valorNormalizado: limpo.toLowerCase() };
    }
    if (regexTelegram.test(limpo)) {
        return { valido: true, tipo: "telegram", valorNormalizado: limpo };
    }
    // Se digitou o username sem @ e sem ponto, adiciona @ automaticamente
    if (/^[a-zA-Z0-9_]{3,32}$/.test(limpo)) {
        return { valido: true, tipo: "telegram", valorNormalizado: "@" + limpo };
    }
    return { valido: false, tipo: null, valorNormalizado: limpo };
}

/* ==========================================================
   LOGIN E TRANSIÇÃO PARA 2FA REAL
========================================================== */
function configurarFormularioLogin() {
    const formLogin = document.getElementById("form-login");
    if (!formLogin) return;

    formLogin.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("auth-alert");

        const inputIdent = document.getElementById("login-identificador");
        const inputSenha = document.getElementById("login-senha");
        const btnEntrar = document.getElementById("btn-entrar");

        const validacao = validarIdentificadorHibrido(inputIdent.value);
        if (!validacao.valido) {
            exibirAlerta("auth-alert", "Informe um E-mail válido ou seu @usuário do Telegram (ex: @meu_usuario).", "error");
            inputIdent.focus();
            return;
        }

        if (!inputSenha.value) {
            exibirAlerta("auth-alert", "Por favor, insira sua senha.", "error");
            inputSenha.focus();
            return;
        }

        btnEntrar.disabled = true;
        btnEntrar.innerHTML = `<span>Autenticando...</span>`;

        try {
            const response = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    identificador: validacao.valorNormalizado,
                    email: validacao.valorNormalizado,
                    senha: inputSenha.value
                })
            });

            const data = await response.json();

            if (response.ok && data.requer_2fa) {
                identificadorPendente2FA = data.identificador || validacao.valorNormalizado;
                document.getElementById("twofa-email-destino").textContent = data.email_mascarado || validacao.valorNormalizado;
                document.querySelectorAll(".otp-input").forEach((inp) => (inp.value = ""));
                mostrarVisao("2fa");

                const msgExtra = data.aviso_smtp ? ` (${data.aviso_smtp})` : "";
                exibirAlerta("auth-alert", `Código de 6 dígitos enviado para ${data.email_mascarado}!${msgExtra}`, "success");
                return;
            }

            if (response.ok && data.sucesso) {
                localStorage.setItem("usuario_logado", JSON.stringify(data.usuario || {}));
                window.location.href = "/pages/dashboard.html";
            } else {
                exibirAlerta("auth-alert", data.erro || "Credenciais inválidas.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro de conexão com o servidor Flask.", "error");
        } finally {
            btnEntrar.disabled = false;
            btnEntrar.innerHTML = `<span>ENTRAR</span><i class="bi bi-arrow-right-short fs-5"></i>`;
        }
    });
}

/* ==========================================================
   INPUTS E VALIDAÇÃO DO CÓDIGO 2FA
========================================================== */
function configurarInputsOTP2FA() {
    const inputs = document.querySelectorAll(".otp-input");

    inputs.forEach((input, index) => {
        input.addEventListener("input", (e) => {
            e.target.value = e.target.value.replace(/[^0-9]/g, "");
            if (e.target.value && index < inputs.length - 1) {
                inputs[index + 1].focus();
            }
        });

        input.addEventListener("keydown", (e) => {
            if (e.key === "Backspace" && !e.target.value && index > 0) {
                inputs[index - 1].focus();
            }
        });

        input.addEventListener("paste", (e) => {
            e.preventDefault();
            const colado = (e.clipboardData || window.clipboardData).getData("text").replace(/[^0-9]/g, "").slice(0, 6);
            colado.split("").forEach((char, i) => {
                if (inputs[i]) inputs[i].value = char;
            });
            const foco = Math.min(colado.length, inputs.length - 1);
            if (inputs[foco]) inputs[foco].focus();
        });
    });

    const btnReenviar = document.getElementById("btn-reenviar-2fa");
    if (btnReenviar) {
        btnReenviar.addEventListener("click", async () => {
            if (!identificadorPendente2FA) return;
            btnReenviar.disabled = true;

            try {
                const res = await fetch("/api/auth/reenviar-2fa", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ identificador: identificadorPendente2FA })
                });
                const data = await res.json();
                if (res.ok && data.sucesso) {
                    const msgExtra = data.aviso_smtp ? ` (${data.aviso_smtp})` : "";
                    exibirAlerta("auth-alert", `Novo código 2FA enviado!${msgExtra}`, "success");
                } else {
                    exibirAlerta("auth-alert", data.erro || "Erro ao reenviar código.", "error");
                }
            } catch (_) {
                exibirAlerta("auth-alert", "Falha ao conectar ao servidor para reenviar código.", "error");
            }

            let seg = 30;
            const timer = setInterval(() => {
                seg--;
                btnReenviar.textContent = `Reenviar em ${seg}s`;
                if (seg <= 0) {
                    clearInterval(timer);
                    btnReenviar.disabled = false;
                    btnReenviar.textContent = "Reenviar código por e-mail";
                }
            }, 1000);
        });
    }
}

function configurarFormulario2FA() {
    const form2FA = document.getElementById("form-2fa");
    if (!form2FA) return;

    form2FA.addEventListener("submit", async (e) => {
        e.preventDefault();
        const codigo = Array.from(document.querySelectorAll(".otp-input")).map((i) => i.value).join("");

        if (codigo.length < 6) {
            exibirAlerta("auth-alert", "Digite os 6 dígitos do código enviado ao seu e-mail.", "error");
            return;
        }

        const btnValidar = document.getElementById("btn-validar-2fa");
        btnValidar.disabled = true;
        btnValidar.innerHTML = `<span>Verificando...</span>`;

        try {
            const res = await fetch("/api/auth/verificar-2fa", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    identificador: identificadorPendente2FA,
                    codigo: codigo
                })
            });

            const data = await res.json();
            if (res.ok && data.sucesso) {
                localStorage.setItem("usuario_logado", JSON.stringify(data.usuario || {}));
                exibirAlerta("auth-alert", "2FA confirmado com sucesso! Entrando...", "success");
                setTimeout(() => {
                    window.location.href = "/pages/dashboard.html";
                }, 800);
            } else {
                exibirAlerta("auth-alert", data.erro || "Código 2FA incorreto ou expirado.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro ao validar o código no servidor.", "error");
        } finally {
            btnValidar.disabled = false;
            btnValidar.innerHTML = `<i class="bi bi-check2-circle"></i><span>VERIFICAR E ACESSAR</span>`;
        }
    });
}

/* ==========================================================
   CADASTRO COM @TELEGRAM OBRIGATÓRIO
========================================================== */
function configurarFormularioCadastro() {
    const formRegister = document.getElementById("form-register");
    if (!formRegister) return;

    formRegister.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("auth-alert");

        const nome = document.getElementById("reg-nome").value.trim();
        const email = document.getElementById("reg-email").value.trim();
        let telegram = document.getElementById("reg-telegram").value.trim();
        const senha = document.getElementById("reg-senha").value;

        if (!nome || !email) {
            exibirAlerta("auth-alert", "Nome e E-mail são obrigatórios.", "error");
            return;
        }

        // Validação estrita do @Telegram obrigatório (RN03)
        if (!telegram) {
            exibirAlerta("auth-alert", "O campo @Telegram é obrigatório para usar o sistema.", "error");
            document.getElementById("reg-telegram").focus();
            return;
        }

        if (!telegram.startsWith("@")) {
            telegram = "@" + telegram;
        }

        if (!/^@[a-zA-Z0-9_]{3,32}$/.test(telegram)) {
            exibirAlerta("auth-alert", "Informe um @Telegram válido (ex: @seu_usuario, mínimo de 3 caracteres).", "error");
            document.getElementById("reg-telegram").focus();
            return;
        }

        if (!senha || senha.length < 6) {
            exibirAlerta("auth-alert", "A senha deve ter no mínimo 6 caracteres.", "error");
            return;
        }

        const btnCadastrar = document.getElementById("btn-cadastrar");
        btnCadastrar.disabled = true;
        btnCadastrar.innerHTML = `<span>Cadastrando...</span>`;

        try {
            const res = await fetch("/api/auth/register", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ nome, email, telegram, senha })
            });

            const data = await res.json();
            if (res.ok && data.sucesso) {
                mostrarVisao("login");
                document.getElementById("login-identificador").value = email;
                exibirAlerta(
                    "auth-alert",
                    "Conta criada com sucesso! Faça seu 1º login para receber o código 2FA no seu e-mail.",
                    "success"
                );
                formRegister.reset();
            } else {
                exibirAlerta("auth-alert", data.erro || "Erro ao realizar cadastro.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro de conexão com o servidor.", "error");
        } finally {
            btnCadastrar.disabled = false;
            btnCadastrar.innerHTML = `<span>CADASTRAR COM SEGURANÇA</span>`;
        }
    });
}

/* ==========================================================
   RECUPERAÇÃO E REDEFINIÇÃO DE SENHA POR E-MAIL
========================================================== */
function configurarFormularioEsqueciSenha() {
    const formEsqueci = document.getElementById("form-esqueci-senha");
    if (!formEsqueci) return;

    formEsqueci.addEventListener("submit", async (e) => {
        e.preventDefault();
        ocultarAlerta("forgot-alert");

        const inputEmail = document.getElementById("recuperar-email");
        const email = inputEmail.value.trim();

        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            exibirAlerta("forgot-alert", "Digite um e-mail válido.", "error");
            return;
        }

        const btnEnviar = document.getElementById("btn-enviar-recuperacao");
        btnEnviar.disabled = true;
        btnEnviar.textContent = "Enviando...";

        try {
            const res = await fetch("/api/auth/recuperar-senha", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email })
            });
            const data = await res.json();

            if (res.ok && data.sucesso) {
                const msgExtra = data.aviso_smtp ? `\n(${data.aviso_smtp})` : "";
                exibirAlerta("forgot-alert", `${data.mensagem}${msgExtra}`, "success");
                formEsqueci.reset();
            } else {
                exibirAlerta("forgot-alert", data.erro || "Não foi possível enviar o e-mail de recuperação.", "error");
            }
        } catch (err) {
            exibirAlerta("forgot-alert", "Erro de comunicação com o servidor.", "error");
        } finally {
            btnEnviar.disabled = false;
            btnEnviar.textContent = "Enviar Link";
        }
    });
}

function configurarFormularioRedefinirSenha() {
    const formReset = document.getElementById("form-reset-password");
    if (!formReset) return;

    formReset.addEventListener("submit", async (e) => {
        e.preventDefault();
        const novaSenha = document.getElementById("nova-senha-reset").value;

        if (!novaSenha || novaSenha.length < 6) {
            exibirAlerta("auth-alert", "A nova senha deve ter pelo menos 6 caracteres.", "error");
            return;
        }

        try {
            const res = await fetch("/api/auth/redefinir-senha", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token: tokenResetUrl, nova_senha: novaSenha })
            });
            const data = await res.json();

            if (res.ok && data.sucesso) {
                window.history.replaceState({}, document.title, "/");
                mostrarVisao("login");
                exibirAlerta("auth-alert", "Senha alterada com sucesso! Faça login com sua nova senha.", "success");
            } else {
                exibirAlerta("auth-alert", data.erro || "Link inválido ou expirado.", "error");
            }
        } catch (err) {
            exibirAlerta("auth-alert", "Erro ao conectar ao servidor.", "error");
        }
    });
}

function exibirAlerta(elementId, mensagem, tipo) {
    const box = document.getElementById(elementId);
    if (!box) return;
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = mensagem;
    box.style.display = "block";
}

function ocultarAlerta(elementId) {
    const box = document.getElementById(elementId);
    if (box) box.style.display = "none";
}