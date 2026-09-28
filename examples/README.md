# Příklady AgenCast

Každá složka je samostatný projekt s vlastními `workflows/`, běhy a výstupy.
- `showcase/`: příspěvek pro fiktivní malou pražírnu a kavárnu Lumen, obrázky, `call` a MCP katalog knih.
- `tutorial/`: řešení a cvičení k [českým tutoriálům](../docs/tutorials/).

Z kořene repozitáře po instalaci AgenCast:
```bash
agencast --project examples/showcase validate ig-post --offline
agencast --project examples/showcase run ig-post -i tema="nová káva" --fake framework/tests/golden/ig-post.yaml
agencast --project examples/tutorial validate tutorial-07-skladani --offline
```

Falešné běhy nepotřebují klíč ani síť. Pro ostré běhy zkopírujte `.env.example` do `.env` v daném projektu a doplňte klíč.
`kontrola-tonu.yaml` je v obou projektech: tutoriál 7 na něm ukazuje skládání scénářů; udržujte kopie shodné.
Instagram MCP v showcase používá ukázkovou adresu, před publikací vyžaduje vlastní server a konfiguraci.
Vlastní obsah a klíče ukládejte mimo repozitář; konfigurace příkladů slouží k výuce.
