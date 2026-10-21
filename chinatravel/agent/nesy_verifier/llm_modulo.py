
import os
import re
import sys

from copy import deepcopy
from chinatravel.agent.base import BaseAgent
from chinatravel.agent.model_usage import usage_snapshot, usage_delta, reported_token_count

from chinatravel.agent.nesy_verifier.shared_repair_loop import run_repair_loop
from chinatravel.agent.nesy_verifier.repair_strategies import create_repair_strategy
from chinatravel.agent.nesy_verifier.initial_state import InitialRepairState
from chinatravel.agent.nesy_verifier.prompts.llm_modulo import INITIAL_PROMPT, BACK_PROMPT
from chinatravel.agent.nesy_verifier.prompts.poi_selection import HOTEL_SELECTION_INSTRUCTION, ATTRACTION_SELECTION_INSTRUCTION, RESTAURANT_SELECTION_INSTRUCTION, TRANSPORT_GO_SELECTION_INSTRUCTION, TRANSPORT_BACK_SELECTION_INSTRUCTION
from chinatravel.agent.nesy_verifier.verifier.commonsense_constraint_nl import collect_commonsense_constraints_error
from chinatravel.agent.nesy_verifier.verifier.personal_constraint_nl import collect_personal_error

import pandas as pd
import ast

from chinatravel.agent.utils import Logger

import numpy as np
import json
from chinatravel.json_utils import repair_json
import time
from tqdm import tqdm

## Calculate the difference between two HH:MM times in minutes.
def calc_time_delta(st_time, ed_time):
    st_h, st_m = int(st_time.split(":")[0]), int(st_time.split(":")[1])
    ed_h, ed_m = int(ed_time.split(":")[0]), int(ed_time.split(":")[1])
    return (ed_m - st_m) + (ed_h - st_h) * 60

## Main LLM-Modulo agent class.
## Inherits shared agent functionality from BaseAgent.
class LLMModuloAgent(BaseAgent):
    ## Initialize the agent and configure its environment, maximum repair attempts, logging directory, and shortlist sizes.
    def __init__(self, **kwargs):
        super().__init__(name="LLM-Modulo", **kwargs)
        ## Environment containing travel data and callable tools.
        self.env = kwargs.get('env', None)
        ## Maximum number of repair attempts after initial generation.
        self.max_steps = kwargs.get('max_steps', 0)
        ## (added) Store the selected repair strategy. None means original ChinaTravel R0.
        self.repair_strategy_name = kwargs.get("repair_strategy", None)
        ## Directory for storing prompts, plans, and error logs.
        ## Sanitize the model name so provider IDs like "openai/gpt-4.1" don't
        ## introduce path separators. On Windows a "/" (or "\\") in a path
        ## component is treated as a directory separator and breaks log creation.
        safe_model_name = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(self.model_name or "model")).strip("_") or "model"
        self.log_dir = os.path.join(self.log_dir, f'llm_modulo-{safe_model_name}')
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        ## Number of candidate options shortlisted for itinerary generation.
        self.num_candidates_intercity_transports = 5 # 10
        self.num_candidates_accommodations = 3 # 10
        self.num_candidates_attractions = 15 # 50
        self.num_candidates_restaurants = 5 # 30

    ## Retrieve all available hotels, attractions, or restaurants for a specified city from the ChinaTravel environment.
    def collect_poi_info_all(self, city, poi_type):

        ## Select the appropriate environment function.
        if poi_type == "accommodation":
            func_name = "accommodations_select"
        elif poi_type == "attraction":
            func_name = "attractions_select"
        elif poi_type == "restaurant":
            func_name = "restaurants_select"
        else:
            raise NotImplementedError

        ## Retrieve the first page of matching travel information.
        poi_info = self.env(
            "{func}('{city}', 'name', lambda x: True)".format(func=func_name, city=city)
        )["data"]
        ## Retrieve additional pages until no more results remain.
        while True:
            info_i = self.env("next_page()")["data"]
            if len(info_i) == 0:
                break
            else:
                poi_info = pd.concat([poi_info, info_i], axis=0, ignore_index=True)

        ## Standardize the cost column name.
        poi_info = poi_info.rename(columns={'cost': 'price'})
        return poi_info

    ## Retrieve available trains or flights between two cities.
    def collect_intercity_transport(self, source_city, target_city, trans_type):
        ## Query the environment for the requested transport type.
        trans_info = self.env(
            "intercity_transport_select('{source_city}', '{target_city}', '{trans_type}')".format(
                source_city=source_city, target_city=target_city, trans_type=trans_type
            )
        )["data"]
        ## Collect all pages of transport results.
        while True:
            info_i = self.env("next_page()")["data"]
            if len(info_i) == 0:
                break
            else:
                trans_info = pd.concat([trans_info, info_i], axis=0, ignore_index=True)
        ## Standardize the transport price column.
        trans_info = trans_info.rename(columns={'Cost': 'price'})
        return trans_info
    
    ## Retrieve transport details between two locations within a city.
    def collect_innercity_transport(self, city, start, end, start_time, trans_type):
        ## Construct the environment's transport query.
        call_str = (
            'goto("{city}", "{start}", "{end}", "{start_time}", "{trans_type}")'.format(
                city=city,
                start=start,
                end=end,
                start_time=start_time,
                trans_type=trans_type,
            )
        )

        ## No transport is required if both locations are identical.
        if start == end:
            return []
        info = self.env(call_str)["data"]

        ## Return when no valid transport solution exists.
        if info == "No solution":
            return info

        if not isinstance(info, list):
            return "No solution"
        
        ## For three-segment journeys, adjust the middle segment's cost according to the number of travellers.
        if len(info) == 3:
            info[1]["price"] = info[1]["cost"]
            info[1]["tickets"] = self.problem["people_number"]
            info[1]["cost"] = info[1]["price"] * info[1]["tickets"]

            info[0]["price"] = info[0]["cost"]
            info[2]["price"] = info[2]["cost"]
        ## For taxi journeys, calculate the number of cars required.
        elif info[0]["mode"] == "taxi":
            info[0]["price"] = info[0]["cost"]
            info[0]["cars"] = int((self.problem["people_number"] - 1) / 4) + 1
            info[0]["cost"] = info[0]["price"] * info[0]["cars"]
        ## Walking journeys retain their original cost.
        elif info[0]["mode"] == "walk":
            info[0]["price"] = info[0]["cost"]

        return info

    # Generate the raw itinerary and reusable repair context.
    def _generate_initial_plan(self, problem, prob_idx):
        ## Redirect standard output and errors to per-problem log files.
        sys.stdout = Logger(
            "{}/problem_{}.log".format(
                self.log_dir, problem["uid"]
            ),
            sys.stdout,
            debug_mode=True,
        )
        sys.stderr = Logger(
            "{}/problem_{}.error".format(
                self.log_dir, problem["uid"]
            ),
            sys.stderr,
            debug_mode=True,
        )
        ## Reset the timer and store the current travel request.
        self.reset_clock()
        self.problem = problem

        ## Reset token usage counters for this problem.
        if hasattr(self.backbone_llm, "reset_usage"):
            self.backbone_llm.reset_usage()
        self.backbone_llm.input_token_count = 0
        self.backbone_llm.output_token_count = 0
        self.backbone_llm.input_token_maxx = 0
        initial_usage_before = usage_snapshot(self.backbone_llm)

        ## Reset timing information and temporary travel data.
        self.llm_inference_time = 0
        self.information_collection_time = 0
        self.memory = {}

        ## Identify the departure city and destination city.
        source_city = problem["start_city"]
        target_city = problem["target_city"]

        ## Retrieve outbound and return train/flight options.
        print(source_city, "->", target_city)
        self.memory["train_go"] = self.collect_intercity_transport(source_city, target_city, "train")
        self.memory["train_back"] = self.collect_intercity_transport(target_city, source_city, "train")
        self.memory["flight_go"] = self.collect_intercity_transport(source_city, target_city, "airplane")
        self.memory["flight_back"] = self.collect_intercity_transport(target_city, source_city, "airplane")
        
        ## Retrieve all available accommodation, attraction, and restaurant information for the destination.
        self.memory["accommodations"] = self.collect_poi_info_all(
            problem["target_city"], "accommodation"
        )
        self.memory["attractions"] = self.collect_poi_info_all(
            problem["target_city"], "attraction"
        )
        self.memory["restaurants"] = self.collect_poi_info_all(
            problem["target_city"], "restaurant"
        )

        ## Ask the LLM to shortlist suitable travel options.
        ## These candidate selections will later be inserted into the itinerary generation and repair prompts.
        selected_go_train_index, selected_go_flight_index = self.select_intercity_transport_go(self.memory["train_go"], self.memory["flight_go"], problem, required_num=self.num_candidates_intercity_transports)        
        selected_back_train_index, selected_back_flight_index = self.select_intercity_transport_back(self.memory["train_back"], self.memory["flight_back"], problem, required_num=self.num_candidates_intercity_transports)
        
        if len(selected_go_train_index) > 0: 
            selected_go_train = self.memory["train_go"].iloc[selected_go_train_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_go_train = "None"
        if len(selected_go_flight_index) > 0:
            selected_go_flight = self.memory["flight_go"].iloc[selected_go_flight_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_go_flight = "None"
        if len(selected_back_train_index) > 0:
            selected_back_train = self.memory["train_back"].iloc[selected_back_train_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_back_train = "None"
        if len(selected_back_flight_index) > 0:
            selected_back_flight = self.memory["flight_back"].iloc[selected_back_flight_index].to_csv(sep='\t', na_rep='nan', index=False)
        else:
            selected_back_flight = "None"

        print("selected go transport: \n", selected_go_train, "\n", selected_go_flight)
        print("selected back transport: \n", selected_back_train, "\n", selected_back_flight)

        selected_accommodation_index = self.select_accommodation(self.memory["accommodations"], problem, required_num=self.num_candidates_accommodations)
        selected_hotel_info = self.memory["accommodations"].iloc[selected_accommodation_index].drop(["id", "hotelname_en"], axis=1).to_csv(sep='\t', na_rep='nan', index=False)
        print("selected hotel: \n", selected_hotel_info)

        selected_attraction_index = self.select_attraction(self.memory["attractions"], problem, required_num=self.num_candidates_attractions)
        selected_attraction_info = self.memory["attractions"].iloc[selected_attraction_index].drop(["id"], axis=1).to_csv(sep='\t', na_rep='nan', index=False)
        print("selected attraction: \n", selected_attraction_info)

        selected_restaurant_index = self.select_restaurant(self.memory["restaurants"], problem, required_num=self.num_candidates_restaurants)
        selected_restaurant_info = self.memory["restaurants"].iloc[selected_restaurant_index].drop(["id"], axis=1).to_csv(sep='\t', na_rep='nan', index=False)
        print("selected restaurant: \n", selected_restaurant_info)
        
        ## Collect shortlisted location names to calculate possible travel connections.
        POI_set = set()
        def add_poi_name(df, key):
            if len(df) > 0:
                for item in df[key]:
                    POI_set.add(item)
        add_poi_name(self.memory["train_go"].iloc[selected_go_train_index], "To")
        add_poi_name(self.memory["flight_go"].iloc[selected_go_flight_index], "To")
        add_poi_name(self.memory["train_back"].iloc[selected_back_train_index], "From")
        add_poi_name(self.memory["flight_back"].iloc[selected_back_flight_index], "From")
        add_poi_name(self.memory["accommodations"].iloc[selected_accommodation_index], "name")
        add_poi_name(self.memory["attractions"].iloc[selected_attraction_index], "name")
        add_poi_name(self.memory["restaurants"].iloc[selected_restaurant_index], "name")

        POI_list = list(POI_set)
        print(POI_list)

        ## Set a fixed random seed for reproducible transport sampling.
        np.random.seed(19260817)

        print(f"collecting innercity transport for {len(POI_list)} POIs ...")
        
        selected_innercity_transport_info = ""
        ## Retrieve transport options between pairs of shortlisted locations.
        for poi_a in tqdm(POI_list):
            for poi_b in POI_list:
                selected_innercity_transport_info += f"from {poi_a} to {poi_b}: "
                for trans_type in ["metro", "taxi", "walk"]:
                    time_str = f"{np.random.randint(10, 20):02d}:{np.random.randint(0, 59):02d}"
                    transports_sel = self.collect_innercity_transport(
                                        target_city,
                                        poi_a,
                                        poi_b,
                                        time_str,
                                        trans_type,
                                        )
                    if transports_sel == "No solution":
                        continue
                    if len(transports_sel) > 0:
                        duration = calc_time_delta(transports_sel[0]["start_time"], transports_sel[-1]["end_time"])
                        cost = 0
                        for item in transports_sel:
                            cost += item["cost"]
                        selected_innercity_transport_info += f"{trans_type}: duration {duration}, cost {cost}. "
                    else:
                        selected_innercity_transport_info += f" {trans_type}: empty. "
                selected_innercity_transport_info += "\n"
        
        ## Record the time spent collecting travel information.
        self.information_collection_time = time.time() - self.start_clock
        
        # query LLM to get initial solution
        ## Store shortlisted travel information for all repair strategies.
        ## R0-R4 will use the same context when repairing itineraries.
        repair_context = {
            "go_train_info": selected_go_train,
            "go_flight_info": selected_go_flight,
            "back_train_info": selected_back_train,
            "back_flight_info": selected_back_flight,
            "attraction_info": selected_attraction_info,
            "restaurant_info": selected_restaurant_info,
            "accommodation_info": selected_hotel_info,
            "innercity_transport_info": selected_innercity_transport_info,
        }

        ## Construct the initial itinerary prompt using travel data and the user's request.
        query_message = INITIAL_PROMPT.format(
            go_train_info=selected_go_train, 
            go_flight_info=selected_go_flight, 
            back_train_info=selected_back_train,
            back_flight_info=selected_back_flight,
            attraction_info=selected_attraction_info,
            restaurant_info=selected_restaurant_info,
            accommodation_info=selected_hotel_info,
            innercity_transport_info=selected_innercity_transport_info,
            query=problem['nature_language'])
        

        
        prompt_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_0_prompt.txt')
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(query_message)

        pre_time = time.time()
        ## Call the LLM to generate the initial itinerary (step 0).
        response = self.backbone_llm([{"role": "user", "content": query_message}],one_line=False)
        self.llm_inference_time += time.time() - pre_time

        
        response = """[{"day": 1,""" + response
        ## Repair the LLM response's JSON formatting before parsing it.
        nl_plan = repair_json(response)
        json_plan = json.loads(nl_plan)

        ## Preserve the raw itinerary before transport translation modifies it.
        raw_plan = deepcopy(json_plan)

        return InitialRepairState(
            query_uid=problem.get("uid"), problem=deepcopy(problem),
            raw_initial_plan=raw_plan, repair_context=deepcopy(repair_context),
            environment_context={"lang": self.lang},
            generation_metadata={
                "raw_response": response,
                "input_tokens": usage_delta(initial_usage_before, usage_snapshot(self.backbone_llm), "input_tokens"),
                "output_tokens": usage_delta(initial_usage_before, usage_snapshot(self.backbone_llm), "output_tokens"),
                "total_tokens": usage_delta(initial_usage_before, usage_snapshot(self.backbone_llm), "total_tokens"),
                "model_calls": usage_delta(initial_usage_before, usage_snapshot(self.backbone_llm), "model_calls"),
                "failed_model_calls": usage_delta(initial_usage_before, usage_snapshot(self.backbone_llm), "failed_model_calls"),
                "elapsed_time_seconds": time.time() - self.start_clock,
                "llm_inference_time_seconds": self.llm_inference_time,
                "information_collection_time_seconds": self.information_collection_time,
            },
        )

    def prepare_initial_repair_state(self, problem, prob_idx=None):
        """Collect, shortlist, generate and verify once; no repairs are performed."""
        from chinatravel.agent.nesy_verifier.shared_repair_loop import verify_plan

        from time import perf_counter
        from chinatravel.agent.system_usage import system_usage_scope, system_delta, verification_execution

        with system_usage_scope() as usage:
            before = usage.snapshot()
            started = perf_counter()
            state = self._generate_initial_plan(problem, prob_idx or problem.get("uid"))
            state.generation_metadata["initial_generation_time_s"] = perf_counter() - started
            state.generation_metadata["initial_generation_tool_calls"] = system_delta(before, usage.snapshot())["tool_call_count"]
            state.generation_metadata["initial_generation_tool_call_counts_by_type"] = system_delta(before, usage.snapshot())["tool_call_counts_by_type"]
            state.initial_verification = verification_execution(verify_plan)(
                state.problem,
                {"people_number": problem["people_number"], "start_city": problem["start_city"],
                 "target_city": problem["target_city"], "itinerary": deepcopy(state.raw_initial_plan)},
                translate_fn=self.translate_innercity_transport,
            )
        return state

    def solve(self, problem, prob_idx, oracle_verifier):
        state = self._generate_initial_plan(problem, prob_idx)
        raw_plan = deepcopy(state.raw_initial_plan)
        json_plan = deepcopy(raw_plan)
        response = state.generation_metadata["raw_response"]
        repair_context = state.repair_context
        selected_go_train = repair_context["go_train_info"]
        selected_go_flight = repair_context["go_flight_info"]
        selected_back_train = repair_context["back_train_info"]
        selected_back_flight = repair_context["back_flight_info"]
        selected_attraction_info = repair_context["attraction_info"]
        selected_restaurant_info = repair_context["restaurant_info"]
        selected_hotel_info = repair_context["accommodation_info"]
        selected_innercity_transport_info = repair_context["innercity_transport_info"]

        ## Use the new shared framework when a repair strategy is selected.
        ## Keep the original ChinaTravel R0 loop unchanged when None.
        if self.repair_strategy_name is not None:

            strategy = create_repair_strategy(self.repair_strategy_name)

            ## Run shared verification and repair.
            loop_result = run_repair_loop(
                problem=problem,
                raw_plan=raw_plan,
                strategy=strategy,
                context=repair_context,
                llm=self.backbone_llm,
                translate_fn=self.translate_innercity_transport,
                max_steps=self.max_steps,
            )

            ## Include the time spent generating repairs.
            self.llm_inference_time += sum(
                attempt.get("metadata", {}).get("llm_inference_time", 0)
                for attempt in loop_result["history"]
            )

            ## Package the final accepted itinerary for ChinaTravel.
            final_verification = loop_result["verification"]
            final_plan = deepcopy(final_verification["translated_plan"])

            ## Add verification results and execution statistics.
            final_plan["error_info"] = final_verification["error_info"]
            final_plan["personal_constraints"] = final_verification["personal_constraints"]
            final_plan["elapsed_time(sec)"] = time.time() - self.start_clock
            final_plan["input_token_count"] = reported_token_count(self.backbone_llm, "input")
            final_plan["output_token_count"] = reported_token_count(self.backbone_llm, "output")
            final_plan["input_token_maxx"] = self.backbone_llm.input_token_maxx
            final_plan["llm_inference_time(sec)"] = self.llm_inference_time
            final_plan["information_collection_time"] = self.information_collection_time

            ## Save the repair history separately for analysis.
            history_path = os.path.join(
                self.log_dir,
                f"problem_{prob_idx}_repair_history.json",
            )
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(
                    loop_result["history"],
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            ## True means a final result was produced, not that all checks passed.
            return True, final_plan

        ## Package the generated itinerary together with timing and token usage statistics.
        evaluated_plan = {
            "people_number": problem["people_number"],
            "start_city": problem["start_city"],
            "target_city": problem["target_city"],
            "itinerary": json_plan, 
            
            "elapsed_time(sec)": time.time() - self.start_clock, 
            "input_token_count": reported_token_count(self.backbone_llm, "input"),
            "output_token_count": reported_token_count(self.backbone_llm, "output"),
            "input_token_maxx": self.backbone_llm.input_token_maxx,
            "llm_inference_time(sec)": self.llm_inference_time, 
            "information_collection_time": self.information_collection_time, 
        }

        print(json_plan)

        # get error info from symbolic feedback
        ## Verify commonsense constraints and collect violation messages.
        error_info = collect_commonsense_constraints_error(problem, evaluated_plan, verbose=False)

        if not "Format Error. Please strictly follow the instructions in the prompt." in error_info:

            try:
                evaluated_plan['itinerary'] = self.translate_innercity_transport(evaluated_plan['itinerary'], problem)
                ## Verify user-specific constraints and append any violations.
                personal_error_info = collect_personal_error(problem, evaluated_plan, verbose=False)

                for pe in personal_error_info:
                    error_info.append(pe)
            except Exception as e:
                print("Error in translating innercity transport: ", e)
                error_info.append("Format Error on Innercity Transport Information. Please strictly follow the instructions in the prompt.")

        
        print("ITER: ", 0, "ERROR:\n", error_info)

        ## Store the verifier's error messages with the evaluated itinerary.
        evaluated_plan["error_info"] = error_info

        json_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_0_plan.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(evaluated_plan, f, indent=4, ensure_ascii=False)

        ## Remove duplicate initial error messages before constructing repair feedback.
        unique_error_info = list(set(error_info))
        error_info_nl = ""
        for item in unique_error_info:
            error_info_nl += item + "\n"
        
        error_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_0_error.err')
        with open(error_file, 'w', encoding='utf-8') as f:
            f.write(error_info_nl)
        
        ## Begin the R0 repair loop, limited to max_steps attempts.
        for step_i in range(1, self.max_steps + 1):            
            
            ## Stop repairing if the current itinerary has no reported errors.
            if (len(error_info) == 0):
                break
                
            # refine the plan with error information
            ## Construct a repair prompt containing the previous plan and verifier feedback.
            query_message = BACK_PROMPT.format(
            go_train_info=selected_go_train, 
            go_flight_info=selected_go_flight, 
            back_train_info=selected_back_train,
            back_flight_info=selected_back_flight,
            attraction_info=selected_attraction_info,
            restaurant_info=selected_restaurant_info,
            accommodation_info=selected_hotel_info,
            innercity_transport_info=selected_innercity_transport_info,
            query=problem['nature_language'],
            plan=response,
            backprompt=error_info_nl
            )
            
            
            prompt_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_{step_i}_prompt.txt')
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(query_message)
            
            pre_time = time.time()
            ## Generate a complete revised itinerary without restricting which slots can change.
            response = self.backbone_llm([{"role": "user", "content": query_message}],one_line=False)
            response = """[{"day": 1,""" + response
            
            self.llm_inference_time += time.time() - pre_time

            nl_plan = repair_json(response)
            json_plan = json.loads(nl_plan)


            evaluated_plan = {
                "people_number": problem["people_number"],
                "start_city": problem["start_city"],
                "target_city": problem["target_city"],
                "itinerary": json_plan, 
                
                "elapsed_time(sec)": time.time() - self.start_clock, 
                "input_token_count": reported_token_count(self.backbone_llm, "input"),
                "output_token_count": reported_token_count(self.backbone_llm, "output"),
                "input_token_maxx": self.backbone_llm.input_token_maxx,
                "llm_inference_time(sec)": self.llm_inference_time, 
                "information_collection_time": self.information_collection_time, 
            }
            ## Reverify the revised itinerary and collect its latest violations.
            error_info = collect_commonsense_constraints_error(problem, evaluated_plan, verbose=False)       

            if not "Format Error. Please strictly follow the instructions in the prompt." in error_info:
                try:
                    evaluated_plan['itinerary'] = self.translate_innercity_transport(evaluated_plan['itinerary'], problem)
                    personal_error_info = collect_personal_error(problem, evaluated_plan, verbose=False)
                
                    for pe in personal_error_info:
                        error_info.append(pe)
                
                except Exception as e:
                    print("Error in translating innercity transport: ", e)
                    error_info.append("Format Error on Innercity Transport Information. Please strictly follow the instructions in the prompt.")


            print("ITER: ", step_i, "ERROR:\n", error_info)
            
            evaluated_plan["error_info"] = error_info
    

            json_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_{step_i}_plan.json')
            ## Save the current iteration's itinerary, errors, and cumulative usage statistics.
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(evaluated_plan, f, indent=4, ensure_ascii=False)

            error_info_nl = ""
            for item in error_info:
                error_info_nl += item + "\n"
            
            error_file = os.path.join(self.log_dir, f'problem_{prob_idx}_step_{step_i}_error.err')
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(error_info_nl)

        ## Return the final evaluated plan; True is not proof that all constraints passed.
        return True, evaluated_plan

    def select_accommodation(self, hotel_info, query, required_num=10):
        
        
        hotel_info = hotel_info.drop(columns=["hotelname_en"])

        # 将 hotel_info 转换为不带索引的字符串
        hotel_info_str = hotel_info.to_csv(sep='\t', na_rep='nan', index=False)


        time_before = time.time()
        # filtering hotel info by llm
        query_message=[{"role": "user", "content": HOTEL_SELECTION_INSTRUCTION.format(required_options=required_num, user_requirements=query["nature_language"], hotel_info=hotel_info_str)}]


        answer = self.backbone_llm(query_message,one_line=False)


        self.llm_inference_time_count += time.time() - time_before

        print(answer)
        
        selected_idx = []
        # if match:
        try:
            HotelNameList = ast.literal_eval(answer)
    
            print('selected HotelNameList: ',HotelNameList) 
            for cand_i in HotelNameList:
                np_where = np.where(hotel_info['name']==cand_i)[0]
                if len(np_where) > 0:
                    selected_index = np_where[0]
                    selected_idx.append(selected_index)
        except Exception as e:
            print("!!!Error in eval HotelNameList:", str(e))
            
            np.random.seed(19260817)
            selected_idx = np.random.choice(len(hotel_info), required_num, replace=False)

        if len(selected_idx) > required_num:
            selected_idx = selected_idx[:required_num]
        return selected_idx
    
    def select_attraction(self, attraction_info, query, required_num=50):


        attraction_info = attraction_info
        # 将 attraction_info 转换为不带索引的字符串
        attraction_info_str = attraction_info.to_csv(sep='\t', na_rep='nan', index=False)


        time_before = time.time()
        query_message=[{"role": "user", "content": ATTRACTION_SELECTION_INSTRUCTION.format(required_options=required_num, user_requirements=query["nature_language"], attraction_info=attraction_info_str)}]

        answer = self.backbone_llm(query_message,one_line=False)
        
        print(answer)

        time_after = time.time()
        selected_idx = []

        try:
            AttrNameList = ast.literal_eval(answer)
            print('selected AttrNameList: ',AttrNameList) 
            for cand_i in AttrNameList:
                np_where = np.where(attraction_info['name']==cand_i)[0]
                if len(np_where) > 0:
                    selected_index = np_where[0]
                selected_idx.append(selected_index)

        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))

            np.random.seed(19260817)
            selected_idx = np.random.choice(len(attraction_info), required_num, replace=False)

        if len(selected_idx) > required_num:
            selected_idx = selected_idx[:required_num]
        return selected_idx
    def select_restaurant(self, restaurant_info, query, required_num=30):


        restaurant_info_str = restaurant_info.to_csv(sep='\t', na_rep='nan', index=False)


        time_before = time.time()
        query_message=[{"role": "user", "content": RESTAURANT_SELECTION_INSTRUCTION.format(required_options=required_num, user_requirements=query["nature_language"], restaurant_info=restaurant_info_str)}]

        answer = self.backbone_llm(query_message,one_line=False)

        print(answer)

        time_after = time.time()
        selected_idx = []

        try:
            RestNameList = ast.literal_eval(answer)
            print('selected RestNameList: ',RestNameList) 
            for cand_i in RestNameList:
                np_where = np.where(restaurant_info['name']==cand_i)[0]
                if len(np_where) > 0:
                    selected_index = np_where[0]
                    selected_idx.append(selected_index)

        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))

            np.random.seed(19260817)
            selected_idx = np.random.choice(len(restaurant_info), required_num, replace=False)

        if len(selected_idx) > required_num:
            selected_idx = selected_idx[:required_num]
        return selected_idx
    
    def select_intercity_transport_go(self, train_info, flight_info, query, required_num=10):
        train_info_str = train_info.to_csv(sep='\t', na_rep='nan', index=False)
        flight_info_str = flight_info.to_csv(sep='\t', na_rep='nan', index=False)
        time_before = time.time()

        query_message=[{"role": "user", "content": TRANSPORT_GO_SELECTION_INSTRUCTION.format(origin=query["start_city"], destination=query["target_city"], required_options=required_num, user_requirements=query["nature_language"], train_info=train_info_str, flight_info=flight_info_str)}]
        answer = self.backbone_llm(query_message,one_line=False)
        print(answer)

        selected_train_idx, selected_flight_idx = [], []
        try:
            TransportList = ast.literal_eval(answer)
            print('selected TransportList: ',TransportList) 
            for cand_i in TransportList:

                if (len(train_info)>0):
                    np_where = np.where(train_info['TrainID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_train_idx.append(np_where[0])
                        
                if (len(flight_info)>0):
                    np_where = np.where(flight_info['FlightID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_flight_idx.append(np_where[0])
            if len(selected_train_idx) > required_num:
                selected_train_idx = selected_train_idx[:required_num]
            if len(selected_flight_idx) > required_num:
                selected_flight_idx = selected_flight_idx[:required_num]

        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))
            np.random.seed(19260817)
            selected_train_idx = np.random.choice(len(train_info), min(len(train_info), required_num // 2), replace=False)
            selected_flight_idx = np.random.choice(len(flight_info), min(len(flight_info), required_num - required_num // 2), replace=False)         

        return selected_train_idx, selected_flight_idx

    def select_intercity_transport_back(self, train_info, flight_info, query, required_num=10):
        train_info_str = train_info.to_csv(sep='\t', na_rep='nan', index=False)
        flight_info_str = flight_info.to_csv(sep='\t', na_rep='nan', index=False)
        time_before = time.time()
        query_message=[{"role": "user", "content": TRANSPORT_BACK_SELECTION_INSTRUCTION.format(origin=query["target_city"], destination=query["start_city"], required_options=required_num, user_requirements=query["nature_language"], train_info=train_info_str, flight_info=flight_info_str)}]
        answer = self.backbone_llm(query_message,one_line=False)
        print(answer)
        selected_train_idx, selected_flight_idx = [], []
        try:
            TransportList = ast.literal_eval(answer)
            print('selected TransportList: ',TransportList)
            for cand_i in TransportList:
                if (len(train_info)>0):
                    np_where = np.where(train_info['TrainID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_train_idx.append(np_where[0])

                if (len(flight_info)>0):
                    np_where = np.where(flight_info['FlightID']==cand_i)[0]
                    if len(np_where) > 0:
                        selected_flight_idx.append(np_where[0])

            if len(selected_train_idx) > required_num:
                selected_train_idx = selected_train_idx[:required_num]
            if len(selected_flight_idx) > required_num:
                selected_flight_idx = selected_flight_idx[:required_num]
                
        except Exception as e:
            print("!!!Error in eval selected_idx:", str(e))
            np.random.seed(19260817)
            selected_train_idx = np.random.choice(len(train_info), min(len(train_info), required_num // 2), replace=False)
            selected_flight_idx = np.random.choice(len(flight_info), min(len(flight_info), required_num - required_num // 2), replace=False)

        return selected_train_idx, selected_flight_idx

    def translate_innercity_transport(self, plan, problem):
        

        for day_activity in plan:
            for activity in day_activity['activities']:
                if 'transports' in activity:
                    if type(activity['transports']) == dict:
                        try:
                            activity['transports']['from']
                            activity['transports']['to']
                            activity['transports']['start_time']
                            activity['transports']['end_time']
                            activity['transports']['mode']
                            activity['transports']['cost']
                            call_str = (
                                    'goto("{city}", "{start}", "{end}", "{start_time}", "{trans_type}")'.format(
                                        city=problem["target_city"],
                                        start=activity['transports']['from'],
                                        end=activity['transports']['to'],
                                        start_time=activity['transports']['start_time'],
                                        trans_type=activity['transports']['mode'], 
                                    )
                                )
                            info = self.env(call_str)["data"]
                            if len(info) == 3:
                                info[1]["price"] = info[1]["cost"]
                                info[1]["tickets"] = self.problem["people_number"]
                                # info[1]["cost"] = info[1]["price"] * info[1]["tickets"]
                                info[1]["cost"] = activity['transports']['cost']
                                

                                info[0]["price"] = info[0]["cost"]
                                info[2]["price"] = info[2]["cost"]
                            elif info[0]["mode"] == "taxi":
                                info[0]["price"] = info[0]["cost"]
                                info[0]["cars"] = int((self.problem["people_number"] - 1) / 4) + 1
                                # info[0]["cost"] = info[0]["price"] * info[0]["cars"]
                                info[0]["cost"] = activity['transports']['cost']

                            elif info[0]["mode"] == "walk":
                                # info[0]["price"] = info[0]["cost"]
                                info[0]["cost"] = activity['transports']['cost']

                            activity['transports'] = info
                    
                        except:
                            activity['transports'] = []
                            continue
                    else:
                        activity['transports'] = []
                    



        return plan
