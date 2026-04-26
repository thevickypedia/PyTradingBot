Release Notes
=============

v0.1.2 (04/26/2026)
-------------------
- `b4e8421 <https://github.com/thevickypedia/PyTradingBot/commit/b4e8421adb76c86dd1d55ac287d8f8b3d6cf3b2c>`_ chore: Release ``v0.1.2``
- `afc4c3e <https://github.com/thevickypedia/PyTradingBot/commit/afc4c3ec260eaafc3199f8b92dce80ca04de43d0>`_ ci: Add a new GHA pipeline to auto-commit release notes
- `fce56ca <https://github.com/thevickypedia/PyTradingBot/commit/fce56ca0906a8f4aa6c19f36f6a808609cf9c994>`_ feat: Update backtest report to run for custom tickers
- `cc15ac5 <https://github.com/thevickypedia/PyTradingBot/commit/cc15ac570edfba0a176fa6954030afb41f36327f>`_ feat: Improve scoring mechanism
- `e1c9d8f <https://github.com/thevickypedia/PyTradingBot/commit/e1c9d8f144beae231aa96572516ffd08d9cf76e0>`_ chore: Update dependencies and typehints

v0.1.1 (04/26/2026)
-------------------
- `610f658 <https://github.com/thevickypedia/PyTradingBot/commit/610f658e923ecdd451c015fa7b847bbf017b0af1>`_ chore: Release ``v0.1.1``
- `fb1e6fe <https://github.com/thevickypedia/PyTradingBot/commit/fb1e6fe148572e6e211fb5532f6fd52108443542>`_ perf: Improve code re-usability
- `aded152 <https://github.com/thevickypedia/PyTradingBot/commit/aded1520023b4f67b19c6c54c97e34bc7d3ede5c>`_ fix: Add missing JSON files in project metadata

v0.1.0 (04/26/2026)
-------------------
- `3c6adcd <https://github.com/thevickypedia/PyTradingBot/commit/3c6adcd4a05434d8f765ebb8381504aacec1ff53>`_ chore: Release ``v0.1.0``
- `9f00fa2 <https://github.com/thevickypedia/PyTradingBot/commit/9f00fa2885afd4af4e83ae432c45c6c5a3d7b138>`_ style: Generate matplotlib images in dark more and night mode ability for backtest report
- `88fb023 <https://github.com/thevickypedia/PyTradingBot/commit/88fb0239ce3971a4beca298e5bd79d0ee389eb90>`_ style: Add a footer and include spacing right after the status in the UI
- `06fbab8 <https://github.com/thevickypedia/PyTradingBot/commit/06fbab897f935521d63b449a594e6b2aa94549d1>`_ feat: Change data structure when versions are listed and show a collapsible view in the UI
- `8557b6e <https://github.com/thevickypedia/PyTradingBot/commit/8557b6eb2dedd02327006ae02fd7d54d41283d99>`_ fix: Reset ``scan_error`` and set ``scan_status`` to proper state to avoid being stuck after an error
- `26b2057 <https://github.com/thevickypedia/PyTradingBot/commit/26b2057ccb4c6f8d3b90c1540d7dab218c645620>`_ style: Remove redundant cooldown seconds display and keep drop-down feature for keys in ``Controls`` tab consistent
- `4e96472 <https://github.com/thevickypedia/PyTradingBot/commit/4e964722f8cf6e2fb9f0d595f9917207111e8987>`_ chore: Update ``.gitignore``
- `9fa14ba <https://github.com/thevickypedia/PyTradingBot/commit/9fa14bac6173b949e9b5e0f37a86a5368bf77b2d>`_ feat: Make filter options a drop down menu
- `22cd43d <https://github.com/thevickypedia/PyTradingBot/commit/22cd43d6f1f8baf004022d0526cfb29f2d2fa369>`_ fix: Use a reliable analyzer and scoring mechanism
- `3710930 <https://github.com/thevickypedia/PyTradingBot/commit/371093018b98663983cf86c454d69c568aec69e5>`_ perf: Include a script to generate backtest report
- `778b714 <https://github.com/thevickypedia/PyTradingBot/commit/778b7142803d969d0024208a8c58a6807a2f0243>`_ feat: Include a feature to add multiple stocks in the UI
- `194460b <https://github.com/thevickypedia/PyTradingBot/commit/194460b70b7da5a59049734f8f22641672e5e3b9>`_ style: Enhance rescan button with cooldown state and disable functionality
- `190483e <https://github.com/thevickypedia/PyTradingBot/commit/190483e88b5ff69b34adc8d23e374616a609a91b>`_ feat: Include a new column to display the source for the metrics
- `6562120 <https://github.com/thevickypedia/PyTradingBot/commit/6562120a6887ef6275bde617e670cb616a6f701a>`_ fix: Avoid gathering metrics for tickers already gathered via finviz screeners
- `1959dff <https://github.com/thevickypedia/PyTradingBot/commit/1959dfff203abbb5845b8b3a34a2e65625ef3121>`_ feat: Include metrics for custom tickers
- `78744f2 <https://github.com/thevickypedia/PyTradingBot/commit/78744f278034698ebd9716708af5d36059652eff>`_ feat: Include an option to add custom tickers via the UI
- `1f869ad <https://github.com/thevickypedia/PyTradingBot/commit/1f869ade7febdab9ca95f0a0131cba0ad64bbe6e>`_ perf: Instantiate ``env`` and ``config`` objects during startup
- `0e6ad26 <https://github.com/thevickypedia/PyTradingBot/commit/0e6ad26ddb9b390344cedcd446eab441a67f1e00>`_ feat: Replace ``shelve`` DB with ``sqlite3`` for cross-platform compatibility
- `11f1413 <https://github.com/thevickypedia/PyTradingBot/commit/11f1413d70d7d32df76c255f47dbd06975bf2b65>`_ refactor: Filter docker health check logs in ``uvicorn``
- `87b4c16 <https://github.com/thevickypedia/PyTradingBot/commit/87b4c16c66eb45b17e85e3e534f710e97adc03ea>`_ feat: Include a ``docker-compose.yml`` file and allow configurable logs and data directories
- `5d6cfd7 <https://github.com/thevickypedia/PyTradingBot/commit/5d6cfd7ba983fbd665918996436b267f3f12249d>`_ perf: Classify env vars and config into objects
- `099622a <https://github.com/thevickypedia/PyTradingBot/commit/099622acd21871ec039965bf2a8174df1242d2ad>`_ feat: Add a new feature to notify via telegram for strong buy/sell

v0.0.31 (03/21/2026)
--------------------
- `9753281 <https://github.com/thevickypedia/PyTradingBot/commit/97532816b30cd13dca8a4e5249888d9b34df7f13>`_ chore: Release ``v0.0.31``
- `c0e3cab <https://github.com/thevickypedia/PyTradingBot/commit/c0e3cabd85eef57ce85e55ba9823580d3853f31c>`_ fix: Add ``--system`` for pip installation in Dockerfile

v0.0.3 (03/21/2026)
-------------------
- `41f3daa <https://github.com/thevickypedia/PyTradingBot/commit/41f3daae256295b6552acf8949014bc557b71f54>`_ chore: Release ``v0.0.3``
- `5826f4b <https://github.com/thevickypedia/PyTradingBot/commit/5826f4bd6b4dfa0980ce37064bdd33f82696f7ed>`_ refactor: Restructure HTML
- `ffadc1f <https://github.com/thevickypedia/PyTradingBot/commit/ffadc1ffc5611ea03f2cfa59d7600b70df047856>`_ feat: Include an option to logout from the UI when ``uiauth`` protection is wrapped
- `0cf5b58 <https://github.com/thevickypedia/PyTradingBot/commit/0cf5b58614925a3400b4c619d77fce48d2f34aea>`_ feat: Include an option to view legacy log files and gray out disabled schedule
- `3a8eb24 <https://github.com/thevickypedia/PyTradingBot/commit/3a8eb24a0966b9d4f890a8c43fab0128fcf65255>`_ fix: Remove ``docker/`` prefix in GHA docker build filepath

v0.0.2 (03/20/2026)
-------------------
- `9557f28 <https://github.com/thevickypedia/PyTradingBot/commit/9557f2808dea54dc575bb4951fc2e908a4a6c25e>`_ chore: Release ``v0.0.2``
- `d9fd6e5 <https://github.com/thevickypedia/PyTradingBot/commit/d9fd6e59d41b131111e0f7bb868b9764558397af>`_ feat: Include a filter in the UI for log level
- `5c08f99 <https://github.com/thevickypedia/PyTradingBot/commit/5c08f99873c200754640dc4309af63b6d10ebbbc>`_ perf: Improve logging
- `e793c7d <https://github.com/thevickypedia/PyTradingBot/commit/e793c7d01bdee1b0eb00e7713e523aa0e8e3ff28>`_ fix: Enhance schedule validation to prevent identical start and end times
- `7c8b05a <https://github.com/thevickypedia/PyTradingBot/commit/7c8b05a637045107211cde2abce3caaebc4cefff>`_ refactor: Update scan source initialization
- `6154862 <https://github.com/thevickypedia/PyTradingBot/commit/6154862e614d5bf129b352d19d6e5b38f97f6018>`_ feat: Add a new feature to include a background task to gather metrics on an overridable schedule
- `5beeb8a <https://github.com/thevickypedia/PyTradingBot/commit/5beeb8a7a7a653f1e5a4ca9706f534e99130b969>`_ docs: Update README.md to include dockerized steps
- `c3aa5f4 <https://github.com/thevickypedia/PyTradingBot/commit/c3aa5f4901b674a149bd89cbcf88259920ab06d1>`_ feat: Dockerize the project

v0.0.1 (03/20/2026)
-------------------
- `f3d3e45 <https://github.com/thevickypedia/PyTradingBot/commit/f3d3e45c8ecc44bf5a50b5636d7fd44eff8485c1>`_ chore: Release ``v0.0.1``
- `1a81458 <https://github.com/thevickypedia/PyTradingBot/commit/1a814585eeb5661fb4cfb0363e5307f89574946e>`_ docs: Update README.md
- `0064201 <https://github.com/thevickypedia/PyTradingBot/commit/0064201c8fa157f9dc10a996b24c1e17205c8d18>`_ feat: Add GHA workflows to build and publish pypi and docker images
- `8609e7b <https://github.com/thevickypedia/PyTradingBot/commit/8609e7b75aaac766b5e2050e9d5331b8fc2b1605>`_ fix: Add missing requirements in ``pyproject.toml``
- `1a0f43a <https://github.com/thevickypedia/PyTradingBot/commit/1a0f43a1a6caf78b72306ea9960002c67ddd275b>`_ feat: Add CLI functionality
- `271d9ca <https://github.com/thevickypedia/PyTradingBot/commit/271d9cae03b390bc65c1b62540dfe1d7f5908243>`_ fix: Rename imports to new project name
- `93d2725 <https://github.com/thevickypedia/PyTradingBot/commit/93d2725d07e37369ee390799902474f707f09350>`_ refactor: Rename the project and upload to pypi
- `50152aa <https://github.com/thevickypedia/PyTradingBot/commit/50152aa53858b7223afe9122e63b7b3ee6e16de6>`_ style: Add favicon and apple images
- `4a1ca2d <https://github.com/thevickypedia/PyTradingBot/commit/4a1ca2d511092560a43b3d8cc3e1f4adc418ad79>`_ lint: Run linter and clean up unused code
- `80c1470 <https://github.com/thevickypedia/PyTradingBot/commit/80c1470aa079887b9ab61a05a73f4e9aa1bb0efc>`_ refactor: Remove the use of twelvedata api
- `8d2a832 <https://github.com/thevickypedia/PyTradingBot/commit/8d2a83257bf4aa261da1268d25dec9682c76d61f>`_ feat: Add optional protection using ``FastAPI-UI-Auth``
- `139a9b6 <https://github.com/thevickypedia/PyTradingBot/commit/139a9b6c96d1a2024d8aa4d76c1cb8883ef2341a>`_ refactor: Introduce ScanStatus enum for improved scan state management
- `aadd0b3 <https://github.com/thevickypedia/PyTradingBot/commit/aadd0b3aea229fe4c9f27f97376cf48bfb694da0>`_ feat: Store status reports in a DB to view multiple versions in the UI
- `d11943e <https://github.com/thevickypedia/PyTradingBot/commit/d11943edd815ddb02fb1edfdbd554a6aeb8b7533>`_ lint: Onboard a pre-commit linter
- `421da93 <https://github.com/thevickypedia/PyTradingBot/commit/421da93dc3dc9bdf37962e7647b3e4ba1c2af9f1>`_ refactor: Add API routes through a common router instead of wrappers and allow port and host through env vars
- `b11c472 <https://github.com/thevickypedia/PyTradingBot/commit/b11c47223e9d726d5aa89235b7a2e394bf3185cc>`_ refactor: Improve variable naming and enhance error handling in API logic
- `54ab08f <https://github.com/thevickypedia/PyTradingBot/commit/54ab08f764d13b6070b86824695abddbca837889>`_ fix: Fix sorting issue in the UI
- `709d8e2 <https://github.com/thevickypedia/PyTradingBot/commit/709d8e2baa848c1be11dc7bf794c47e7188df304>`_ feat: Create an API and UI for to view metrics interactively
- `8d76783 <https://github.com/thevickypedia/PyTradingBot/commit/8d76783d79d0bb1d8f58d504a0bc2c9d4e1c715d>`_ refactor: Make conditions explicit
- `34ec3da <https://github.com/thevickypedia/PyTradingBot/commit/34ec3da8e068be0e9f36f186a9d39536309692ee>`_ feat: Add base project
- `880c124 <https://github.com/thevickypedia/PyTradingBot/commit/880c124cbc1e82bd6968e2a4dbd1d2c7f93cd664>`_ Initial commit
