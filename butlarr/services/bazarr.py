from loguru import logger
from typing import Optional, List, Any, Literal
from dataclasses import dataclass, replace

from . import ArrService, ArrVariant, Action, ServiceContent, find_first
from .ext import ExtArrService, QueueState
from ..tg_handler import command, callback, handler
from ..tg_handler.message import (
    Response,
    repaint,
    clear,
)
from ..tg_handler.auth import authorized, AuthLevels, get_auth_level_from_message
from ..tg_handler.session_state import (
    sessionState,
    default_session_state_key_fn,
)
from ..tg_handler.keyboard import Button, keyboard


@dataclass(frozen=True)
class State:
    items: List[Any]
    index: int
    media_id: int
    menu: Optional[
        Literal["list"] | Literal["addsub"]
    ]
    service: ArrService = None


@handler
class Bazarr(ExtArrService, ArrService):
    def __init__(
        self,
        commands: List[str],
        api_host: str,
        api_key: str,
        name: str = None,
        addons: List[ArrService] = []
    ):
        self.commands = commands
        self.api_key = api_key
        
        self.api_version = self.detect_api(api_host)
        self.service_content = ServiceContent.SUBTITLES
        self.arr_variant = ArrVariant.BAZARR

        self.name = name
        self.supported_addons = []
        self.addons = addons

        self.current_service = None
        
    
    @keyboard
    def keyboard(self, state: State, allow_edit=False):

        rows_menu = []
        if len(state.items) > 0:
            row_navigation = [Button("=== Subtitles ===", "noop")]
        else:
            row_navigation = [Button("=== No subtitles found ===", "noop")]

        current_index = 0
        for item in state.items:
            description = f"[Score: {item['score']}]"
            description += f" {item['release_info'][0]}"
            description = description[0:1024]
            rows_menu.append(
                [
                    Button(
                        description,
                        self.get_clbk("addsub", state.index),
                    ),
                ]
            )
            current_index = current_index + 1
            if current_index >= 5: break

        rows_action = []
        if state.menu and state.service:
            rows_action.append([Button("🔙 Back", state.service.get_clbk("addmenu"))])
        elif state.menu:
            rows_action.append([Button("🔙 Back", state.service.get_clbk("goto"))])
        else:
            rows_action.append([Button("❌ Cancel", self.get_clbk("cancel"))])

        return [row_navigation, *rows_menu, *rows_action]


    def detect_api(self, api_host):
        status = None
        # Detect version and api_url
        try:
            self.api_url = f"{api_host.rstrip('/')}/api"
            status = self.request("system/status")
        finally:
            if status is None:
                logger.error(
                    "Could not reach compatible api. Is the service down? Is your API key correct?"
                )
                exit(1)
            assert (
                status
            ), "Could not reach compatible api. Is the service down? Is your API key correct?"
            api_version = status.get("data", {}).get("bazarr_version", "")
            assert api_version, "Could not find compatible api."
            return api_version
    
    
    def lookup(self, arrvariant, id):
        if arrvariant == ArrVariant.RADARR:
            status = self.request('providers/movies', params={'radarrid': id}, fallback=[])
            return status.get('data') if len(status) > 0 else status
        else:
            logger.error(
                f"Bazarr integration not Implemented"
            )
            

    def add(
        self,
        service,
        id,
        item=None,
        options={},
    ):
        assert item, "Missing required arg! You need to provide a item!"

        if service == 'radarr':
            
            params = {
                "radarrid": id, 
                "hi": item.get('hearing_impaired'), 
                "forced": item.get('forced'),
                "original_format": item.get('original_format'),
                "provider": item.get('provider'),
                "subtitle": item.get('subtitle'),
                **options
            }

            return self.request(
                'providers/movies',
                action=Action.POST,
                params=params,
                raw=True
            )
        else:
            logger.error(
                f"Bazarr integration with service {service} is Not Implemented"
            )

    
    def create_message(self, state: State, full_redraw=False, allow_edit=False):
        if not state.items:
            keyboard_markup = self.keyboard(state, allow_edit=allow_edit)

            return Response(
                caption='',
                reply_markup=keyboard_markup,
                state=state,
            )

        item = state.items[state.index]

        keyboard_markup = self.keyboard(state, allow_edit=allow_edit)

        return Response(
            caption='',
            reply_markup=keyboard_markup,
            state=state,
        )


    @repaint
    @callback(
        cmds=[
            "goto"
        ]
    )
    @sessionState()
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_update(self, update, context, args, state):
        auth_level = get_auth_level_from_message(self.db, update)
        allow_edit = auth_level >= AuthLevels.MOD.value
        # Prevent any changes from being made if in library and permission level below MOD
        if args[0] in ["addsub"]:
            item = state.items[state.index]
            if "id" in item and item["id"] and not allow_edit:
                # Don't do anything, illegal operation
                return self.create_message(state, allow_edit=False)

        full_redraw = False
        print(args)
        if args[0] == "goto":
            if len(args) > 1:
                idx = int(args[1])
                item = state.items[idx]
                state = replace(
                    state,
                    index=idx,
                    menu=None,
                )
                full_redraw = True
            else:
                print(state)
                state = replace(state, menu=None)
                print(state)
        return self.create_message(
            state, full_redraw=full_redraw, allow_edit=allow_edit
        )

    @repaint
    @command(default=True)
    @sessionState(init=True)
    @callback(cmds=["list"])
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_list(self, update, context, args):
        print(args)
        media_id = args[1]

        service = self.current_service
        if service:
            arrvariant = service.arr_variant
        else:
            arrvariant = args[2]

        items = self.lookup(arrvariant=arrvariant, id=media_id)

        state = State(
            items=items,
            index=0,
            media_id=media_id,
            service=service,
            menu="list",
        )

        self.session_db.add_session_entry(
            default_session_state_key_fn(self, update), state
        )

        auth_level = get_auth_level_from_message(self.db, update)
        allow_edit = auth_level >= AuthLevels.USER.value
        return self.create_message(state, full_redraw=False, allow_edit=allow_edit)

    @callback(cmds=["addsub"])
    @sessionState(clear=True)
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_add(self, update, context, args, state):
        if state.service:
            arrvariant = state.service.arr_variant
        else:
            arrvariant = args[1]

        result = self.add(
            id = state.media_id,
            service=arrvariant,
            item=state.items[state.index]
        )

        if result.status_code < 200 \
           or result.status_code > 299:
            return Response(caption=f"Something went wrong... {result.content}")

        return Response(caption="Subtitle added!")

    @callback(cmds=["cancel"])
    @sessionState(clear=True)
    @authorized(min_auth_level=AuthLevels.USER)
    async def clbk_cancel(self, update, context, args, state):
        return Response(caption="Subtitle Search canceled!")
    
    def addon_buttons(self, state, service): 
        item = state.items[state.index]
        downloaded = True if "movieFile" in item else False

        # can't pass Service object as *args to get_clbk
        self.current_service = service
        
        buttons = []
        if state.menu == "add" and downloaded:
            buttons.append(
                Button(
                    f"Subtitles",
                    self.get_clbk("list", item.get("id"))
                ),
            )
        return buttons
