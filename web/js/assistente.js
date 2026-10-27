// assistente.js
// Controla as interações com o Chat da IA mantendo as mensagens do usuário visíveis

document.addEventListener("DOMContentLoaded", function () {
    carregarNomeUsuario();
    
    const chatForm = document.getElementById("chatForm");
    const userInput = document.getElementById("userInput");
    const chatMessages = document.getElementById("chatMessages");

    chatForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        const mensagemTexto = userInput.value.trim();

        if (!mensagemTexto) return;

        // 1. Adiciona explicitamente a mensagem do usuário e guarda o ID dela
        adicionarMensagem(mensagemTexto, "user");
        userInput.value = "";

        // 2. Cria indicador temporário de "Pensando..."
        const idCarregando = adicionarMensagem("Analisando seus dados...", "bot loading");

        try {
            const response = await fetch('/perguntar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ msg: mensagemTexto })
            });

            // Remove o balão de "Pensando..."
            removerMensagem(idCarregando);

            const dados = await response.json();

            if (response.ok) {
                // 3. Adiciona a resposta da IA mantendo a do usuário na tela
                adicionarMensagem(dados.resposta || "Recebi sua mensagem!", "bot");
            } else {
                adicionarMensagem(`Erro do servidor: ${dados.resposta || 'Desconhecido'}`, "bot");
            }
        } catch (error) {
            removerMensagem(idCarregando);
            console.error("Erro na comunicação com a IA:", error);
            adicionarMensagem("Erro de conexão: Verifique se o servidor Flask está rodando.", "bot");
        }
    });

    function adicionarMensagem(texto, tipo) {
        const divMensagem = document.createElement("div");
        divMensagem.className = `message ${tipo}`;
        
        const idUnico = 'msg-' + Date.now() + '-' + Math.random();
        divMensagem.id = idUnico;

        divMensagem.innerHTML = `
            <div class="message-content">
                ${texto}
            </div>
        `;

        chatMessages.appendChild(divMensagem);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return idUnico;
    }

    function removerMensagem(id) {
        const elemento = document.getElementById(id);
        if (elemento) elemento.remove();
    }

    function carregarNomeUsuario() {
        const savedName = localStorage.getItem("financeControl_userName") || "Usuário";
        const loggedUserName = document.getElementById("loggedUserName");
        if (loggedUserName) {
            loggedUserName.textContent = `Olá, ${savedName}`;
        }
    }
});